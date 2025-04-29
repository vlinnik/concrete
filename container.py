from pyplc.sfc import *
from pyplc.pou import POU
from pyplc.utils.trig import FTRIG,TRIG
from pyplc.utils.misc import TOF
from .counting import Counter,Flow, RotaryFlowMeter,Expense,Delta

# @sfc(inputs=['m','sp','go','closed','lock'],outputs=['out'],vars=['min_ff','min_w','max_ff','max_w','busy','e','done','err'],hidden=['m','closed','lock'],persistent=['min_ff','max_ff','min_w','max_w','e'])
class Container( SFC ):
    """Расходный бункер"""
    m = POU.input(0.0,hidden=True)
    sp = POU.input(0.0)
    go = POU.input(False)
    closed = POU.input(False,hidden=True)
    lock = POU.input(False,hidden=True)
    out = POU.output(False)
    min_ff = POU.var(0.0,persistent=True)
    max_ff = POU.var(0.0,persistent=True)
    min_w = POU.var(100,persistent=True)
    max_w = POU.var(100,persistent=True)
    e = POU.var(0.0,persistent=True)
    busy = POU.var(False)
    done = POU.var(0.0)
    err = POU.var(0.0)

    def __init__(self, m=0.0, sp = 0.0, go = False, out= False, lock=False, closed=True,max_sp: float = 1000,id:str = None, parent: POU = None) -> None:
        super().__init__( id,parent)
        self.go = go
        self.m = m
        self.sp = sp
        self.min_ff = 300
        self.max_ff = 300
        self.max_sp = max_sp
        self.min_w = 100
        self.max_w = 500
        self.closed = closed
        self.out = out
        self.fast = False
        self.ready = True
        self.busy = False
        self.manual = True
        self.autotune = False   # автоопределение параметров дозирования
        self.f_go = FTRIG(clk = lambda: self.go )
        self.e = 0.0 #maxium posible error
        self.err = 0.0  #accumulated error 
        self.done = 0.0 #amount inside dosator
        self.__counter = Counter(m = m, flow_in= lambda: self.afterOut.q )
        self.q = self.__counter.q
        self.take = None
        self.lock = lock
        self.afterOut = TOF( clk=self._unsealed, pt=3000 )
        self.subtasks = (self.__counting,self.__lock, self.afterOut )

    def _unsealed(self): 
        return self.out or not self.closed
    
    def switch_mode(self,manual: bool):
        self.log(f'ручной режим = {manual}')
        self.manual = manual
        self.out = False
        
    def emergency(self,value: bool = True ):
        self.log(f'аварийный режим = {value}')
        self.out = False
        self.sfc_reset = value
    
    def __lock(self):
        if self.lock:
            self.out = False
    
    def __counting(self):            
        if self.__counter is None:
            return

        self.__counter( )
        self.done=self.__counter.live

    def __auto(self,out=None):
        if out is not None and not self.manual:
            self.out = out and not self.lock

    def install_counter(self,flow_out: callable = None,*args,**kwargs):
        self.__counter.reset_when(flow_out)

    def collect(self,sp=None):
        if sp:
            self.sp = sp
        if not self.ready:
            return
        self.ready = False
        self.f_go( clk = True )

    def __ff(self,sp):
        if sp<=self.min_ff or self.max_sp==0:
            return self.min_ff
        elif sp>=self.max_sp:
            return self.max_ff
        else:
            return sp/self.max_sp*(self.min_ff-self.max_ff)+self.max_ff
    
    def __rought(self,sp,from_m = None):
        self.fast = True
        self.sp = sp
        from_m = self.m if from_m is None else from_m
        if self.take is not None and self.take>0:
            from_m-= self.take 
        self.log(f'грубый режим с {self.m} кг')
        from_T = POU.NOW
        for _ in self.till( lambda: self.m<=from_m+self.sp-self.__ff(self.sp),step='rought'):
            if self.autotune and self.closed:
                from_T = self.time( )
                
            if self.autotune and self.m>=from_m+self.max_sp*0.05:
                self.__auto(False)
                till_T =self.time()
                m0 = self.m
                yield from self.until( lambda: self.closed, min=3000,step = 'autotuning' )
                self.log(f'подстройка {m0}/{self.m}, {till_T - from_T} нсек')
                self.max_ff = (self.m - from_m - self.max_sp*0.05)
                self.min_ff = self.max_ff * 1.1
                self.max_w = max((till_T - from_T)/3000000,100)
                self.min_w = max(self.max_w/10,100)
                self.autotune = False
                self.log(f'рекомендованы min_ff/max_ff/min_w/max_w: {self.min_ff}/{self.max_ff}/{self.min_w}/{self.max_w}')
            self.__auto(True)
            yield
            
        self.__auto(False)
        self.fast = False
        yield from self.until( lambda: self.closed,min=3000 ,step = 'after.rought')

    def __precise(self,sp,from_m=None):
        self.fast = False
        self.sp = sp
        from_m = self.m if from_m is None else from_m
        if self.take is not None and self.take>0:
            from_m -= self.take 
        self.log(f'точный режим с {self.m} кг')
        while self.m<from_m+self.sp*0.99-self.e:
            dm = self.sp+from_m-self.m
            if self.min_ff>0 and dm<=self.min_ff:
                w = dm/self.min_ff*(self.max_w-self.min_w)+self.min_w
            elif self.min_ff<=0:
                w = self.min_w
            else:
                w = self.max_w
            for _ in self.pause( w ):
                self.__auto( True )
                yield 
            for _ in self.until(lambda: self.closed, min=3000,step='pulse.low'):
                self.__auto( False )
                yield
    
    def main(self) :
        self.log(f'готов')
        self.busy = False    
        self.ready= True
        yield from self.until( self.f_go ,step='ready')
        self.ready= False
        self.busy = True
        from_m = self.m 
        yield from self.__rought( self.sp )
        yield from self.__precise( self.sp, from_m=from_m )
        yield from self.until(lambda: self.closed, min=2,max=2 ,step = 'stab')
        if self.sp>0:
            self.err = (self.m - (from_m + self.sp - (self.take if self.take is not None and self.take>0 else 0)) ) 
            self.log(f'завершено на {self.m:.2f} кг, погрешность={(self.err)/self.sp*100:.1f}%')
        self.take = None
    
class FlowMeter(SFC):
    sp = POU.var(0.0)
    go = POU.input(False)
    closed = POU.input(False)
    clk = POU.input(False)
    cnt = POU.input(int(0))     #счетчик импульсов
    out = POU.output(False)
    busy = POU.var(False)
    e = POU.var(0.0,persistent=True)
    done=POU.var(0.0)
    err = POU.var(0.0)
    man = POU.var(False)
    imp_kg = POU.var(0,persistent=True)
    ff = POU.var(0,persistent=True)
    def __init__(self, clk:bool=False,go: bool = None, closed:bool=None,out:bool=None,cnt:int = None,impulseWeight:float = None,max_sp:float = 10, id:str=None,parent:POU=None) -> None:
        super().__init__( id,parent )
        self.sp = 0.0
        self.go = go
        self.closed = closed
        self.out = out
        self.manual = True
        self.ready = True
        self.busy = False
        self.clk = clk
        self.cnt = cnt
        self.impulseWeight = impulseWeight if impulseWeight is not None else 0.0035
        self.loaded = False
        self.unloaded = False   #pulse after accomplishing collect
        self.f_go = FTRIG(clk = lambda: self.go or self.man )
        self.e = 0.0    #maxium posible error
        self.err = 0.0  #accumulated error 
        self.done = 0.0 #amount inside dosator
        self.afterOut = TOF( id='afterOut', clk=lambda: self.out or not self.closed, pt=2000 )
        self._counter = RotaryFlowMeter(weight=self.impulseWeight,clk=TRIG(clk=lambda: self.clk), cnt = lambda: self.cnt, flow_in = lambda: self.afterOut.q )
        self.q = self._counter.q
        self.subtasks = [self.afterOut, self._counting]
        self.max_sp = max_sp

    def switch_mode(self,manual: bool):
        self.log(f'ручной режим = {manual}')
        self.manual = manual
        self.out = False
        
    def emergency(self,value: bool = True ):
        self.log(f'аварийный режим = {value}')
        self.out = False
        self.err = 0
        self.sfc_reset = value

    def _counting(self):
        if self._counter is None:
            return

        self._counter()
        self.done=self._counter.e
            
    def remote(self,out=None):
        self.__auto(out)

    def __auto(self,out=None):
        if out is not None and not self.manual:
            self.out = out

    def install_counter(self,flow_out : callable = None,*args,**kwargs):
        self._counter.reset_when(flow_out)
        delta = Delta(flow_in = self._counter.q,out = flow_out) 
        self.q = delta.q
        self.subtasks+=(delta,)

    def collect(self,sp=None):
        if sp:
            self.sp = sp
        if not self.ready:
            return
        self.ready = False
        self.f_go( clk = True )
        
    def progress(self):
        from_m = self.done
        self.log(f'набор {from_m} до {from_m+self.sp}')
        for x in  self.till( lambda: self.done<from_m + self.sp-self.err - self.ff ):
            self.__auto( out = True )
            yield x
        self.__auto( out = False )
        if self.closed is not None:yield from self.until( lambda: self.closed,min=2000 )
        self.err = self.done - self.sp + self.err
        self.log(f'набор закончен, итог: {self.done}')
        
    def main(self) :
        self.log(f'готов')
        self.busy = False
        if self.imp_kg>0: 
            self.impulseWeight = 1.0/self.imp_kg
            if self._counter is not None: self._counter.weight = self.impulseWeight
            
        for x in self.until( self.f_go ):
            self.busy = False
            self.ready= True
            yield x
        self.ready= False
        self.busy = True
        yield from self.progress( )
        self.loaded = True
        self.unloaded = True
        yield True
        self.unloaded = False        
        self.loaded = False

class Accelerator():
    def __init__(self, outs: list[callable], sts: list[callable] = [],turbo = True, best:int = None ):
        """Создать ускоритель набора из группы затворов

        Args:
            outs (list[callable]): Управляющие сигналы затворами
            sts (list[callable], optional): Обратная связь по затворам. Defaults to [].
            turbo (bool, optional): Режим быстрого набора - из всех затворов сразу. Defaults to True.
            best (int, optional): Номер затвора, которым надо добирать. Defaults to None.
        """        
        self.en = True
        self.cnt = len(outs)  #сколько доступно затворов
        self.src = None       #основной бункер
        self.outs = outs      #все затворы в помощь  
        self.sts = sts        #обратная связь по затворам
        self.cur = 0          #номер затвора что сейчас открывается/будет открываться
        self.nxt = 0          #кто на очереди
        self.out = False      #выход в обычном режиме 
        self.closed = True    #состояние обобщенное
        self.turbo = turbo
        self.best = best
        self.dis = [ f'disable_{i}' for i in range(1,self.cnt+1)]
        self.man = [ f'out_{i}' for i in range(1,self.cnt+1)]
    
    def link(self,src: Container):
        self.src = src
        for i in range(1,self.cnt+1):
            src.export(f'out_{i}',False)
            src.export(f'disable_{i}',False)
            
    def manual(self,index: int):
        return getattr(self.src,self.man[index])
    
    def disabled(self,index: int):
        return getattr(self.src,self.dis[index])

    def __call__(self):
        if self.src is None or not self.en:
            return
        i = 0
        self.closed = True
        for o in self.sts:
            self.closed = self.closed and o() or self.disabled(i)
            i+=1
        
        self.out = False
        if self.src.manual:    
            i = 0
            for o in self.outs:
                self.out = self.out or (not self.src.lock and self.manual(i))
                o( not self.src.lock and self.manual(i))
                i+=1
        elif self.src.fast:
            i = 0
            for o in self.outs:
                self.out = self.out or (self.src.out and not self.disabled(i) and not self.src.lock)
                if not self.disabled(i):
                    o(self.src.out and not self.src.lock)
                    if not self.turbo: break
                i+=1
        else:
            if self.src.out:
                i = 0
                self.nxt = self.cur
                for o in self.outs:
                    o(False)
                    i+=1
                    if self.nxt==self.cur and not self.disabled((self.cur+i) % self.cnt ):
                        self.nxt = (self.cur+i) % self.cnt
                self.out = not self.disabled(self.cur)
                self.outs[self.cur](self.out)
            else:
                for o in self.outs:
                    o(False)
                self.cur = self.nxt if self.best is None else self.best
                
class Retarder(SFC):
    """Замедлитель-объединитель нескольких затворов в один. 
    
    Для случаев, когда на конвейере несколько бункеров с одним компонентом, и дозировать надо всеми затворами поочереди.
    Например 3 бункера песка, доза 1400 а под один затвор помещается только 500 кг. Используя Retarder при открывании 2
    бункера автоматически будут открываться по очереди 2-3-1-2-3 (используя ограничение по времени maxT мсек и dm кг)
    """
    m = POU.input(0.0,hidden=True)
    dm= POU.var(500.0,persistent=True)
    en= POU.var(True,persistent=True)
    
    def __init__(self, m: float, outs: tuple[callable], sts: tuple[callable] = (),turbo = True, best:int = None , id: str=None, parent: POU = None):
        """Создать замедлитель набора из группы затворов

        Args:
            outs (list[callable]): Управляющие сигналы затворами (etc FILLER_OPEN_1)
            sts (list[callable], optional): Обратная связь по затворам (etc FILLER_CLOSED_1). Defaults to [].
            turbo (bool, optional): Режим быстрого набора - из всех затворов сразу. Defaults to True.
            best (int, optional): Номер затвора, которым надо добирать. Defaults to None.
        """        
        super().__init__(id=id,parent=parent)
        self.cnt = len(outs)  #сколько доступно затворов
        self.outs = outs      #все затворы в помощь  
        self.sts = sts        #обратная связь по затворам
        self.cur = None       #номер затвора что сейчас открывается/будет открываться
        self._outs=[False]*self.cnt #что хочет выдать пользователь
        self._sts =[False]*self.cnt #какое состояние датчиков положения подсунем пользователю
        self._lock=[False]*self.cnt #блокировка затвора
        self.turbo = turbo
        self.best = best
        self.m = m
        self.maxT = 5000

        for i in range(1,self.cnt+1):
            self.export(f'disable_{i}',False)
    
    def out(self,index: int):
        """Получить функцию управления затвором по номеру

        Args:
            index (int): номер затвора
        """
        def __out__(value: bool):
            self._outs[index]=value
        return __out__
        
    def closed(self,index: int):
        """получить функцию получения состояния затвора

        Args:
            index (int): номер затвора
        """
        def __closed__()->bool:
            return self._sts[index]
        return __closed__
    
    def lock(self,index: int):
        return self._lock[index]
    
    def __sts(self,on:bool=False):
        if self.cur is not None and self.en:
            for i in range(self.cnt):
                self._sts[i]=True
            if self.sts:
                for _ in self.sts:
                    self._sts[self.cur] = self._sts[self.cur] and _()
            else:
                for _ in self._outs:
                    self._sts[self.cur] = self._sts[self.cur] and _
        else:
            for i in range(self.cnt):
                if self.sts:
                    self._sts[i]=self.sts[i]( )
                else:
                    self._sts[i]=not self._outs[i]
    
    def main(self):
        if not self.en:
            for i in range(self.cnt):
                if self.sts:
                    self._sts[i]=self.sts[i]( )
                else:
                    self._sts[i]=not self._outs[i]
                self.outs[i](self._outs[i])
            for i in range(self.cnt):
                self._lock[i]=False
                for j in range(self.cnt):
                    if i!=j: 
                        self._lock[i] = self._lock[i] or not self._sts[j]
        else:
            for i in range(self.cnt):
                if self._outs[i]:
                    for j in range(self.cnt):
                        if i!=j:
                            self._lock[j]=True

                    j = i
                    self.cur = i
                    while self._outs[i]:
                        till = self.m + self.dm
                        yield from self.till( lambda: self.m<till and self._outs[i],max=self.maxT,n=[self.outs[j],self.__sts])
                                                
                        j=(j+1) % self.cnt
                        while getattr(self,f'disable_{j+1}'):
                            j=(j+1) % self.cnt
                            yield
                        
                    for j in range(self.cnt):
                        self._lock[j]=False
                    
                    break
                else:
                    self.__sts()

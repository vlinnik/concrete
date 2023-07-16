from pyplc.sfc import *
from pyplc.stl import *
from pyplc.utils.trig import FTRIG
from pyplc.utils.misc import TOF
from .counting import Counter,Flow, RotaryFlowMeter

@sfc(inputs=['m','sp','go','closed','lock'],outputs=['out'],vars=['min_ff','min_w','max_ff','max_w','busy','e','done','err'],hidden=['m','closed','lock'],persistent=['min_ff','max_ff','min_w','max_w','e'])
class Container( SFC ):
    """Расходный бункер
    """
    def __init__(self, m=0.0, sp = 0.0, go = False,lock=False, closed=True,max_sp: float = 1000) -> None:
        self.go = go
        self.m = m
        self.sp = sp
        self.min_ff = 300
        self.max_ff = 300
        self.max_sp = max_sp
        self.min_w = 100
        self.max_w = 500
        self.closed = closed
        self.out = False
        self.fast = False
        self.ready = True
        self.busy = False
        self.manual = True
        self.autotune = False   # автоопределение параметров дозирования
        self.f_go = FTRIG(clk = lambda: self.go )
        self.e = 0.0 #maxium posible error
        self.err = 0.0  #accumulated error 
        self.done = 0.0 #amount inside dosator
        self.q = None
        self.__counter = None 
        self.take = None
        self.lock = lock
        self.afterOut = TOF( id='afterOut', clk=lambda: self.out or not self.closed, pt=3000 )
        self.subtasks = [self.__counting,self.__lock,self.afterOut]
    
    def switch_mode(self,manual: bool):
        self.log(f'toggle manual = {manual}')
        self.manual = manual
        self.out = False
        
    def emergency(self,value: bool = True ):
        self.log(f'emergency = {value}')
        self.out = False
        self.sfc_reset = value
    
    def __lock(self):
        self.out = self.out and not self.lock
    
    def __counting(self):            
        if self.__counter is None:
            return

        self.q( clk=self.__counter.q.clk, m = self.__counter.q.m )
        self.__counter( )
        self.done=self.__counter.e

    def __auto(self,out=None):
        if out is not None and not self.manual:
            self.out = out and not self.lock

    def install_counter(self,flow_out: callable = None, m: callable = None):
        self.__counter = Counter(m = m, flow_in= lambda: self.afterOut.q ,flow_out = flow_out)
        self.q = self.__counter.q
       
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
        if self.take>0:
            from_m-= self.take 
        self.log(f'in rought mode from {from_m}')
        from_T = self.time()
        for x in self.till( lambda: self.m<=from_m+self.sp-self.__ff(self.sp),step='rought'):
            if self.autotune and self.closed:
                from_T = self.time( )
                
            if self.autotune and self.m>=from_m+self.max_sp*0.05:
                self.__auto(False)
                till_T =self.time()
                m0 = self.m
                for y in self.until( lambda: self.closed, min=3000,step = 'autotuning' ):
                    yield y
                self.log(f'tuning stop at {m0}/{self.m}, {till_T - from_T} msec')
                self.max_ff = (self.m - from_m - self.max_sp*0.05)
                self.min_ff = self.max_ff * 1.1
                self.max_w = max((till_T - from_T)/3,100)
                self.min_w = max(self.max_w/10,100)
                self.autotune = False
                self.log(f'Tuning result min_ff/max_ff/min_w/max_w: {self.min_ff}/{self.max_ff}/{self.min_w}/{self.max_w}')
            self.__auto(True)
            yield True
            
        self.__auto(False)
        self.fast = False
        for x in self.until( lambda: self.closed,min=3000 ,step = 'after.rought'):
            yield True

    def __precise(self,sp,from_m=None):
        self.fast = False
        self.sp = sp
        from_m = self.m if from_m is None else from_m
        if self.take>0:
            from_m -= self.take 
        self.log(f'in precise mode from {from_m}')
        while self.m<from_m+self.sp*0.99:
            dm = self.sp+from_m-self.m
            if self.min_ff>0 and dm<=self.min_ff:
                w = dm/self.min_ff*(self.max_w-self.min_w)+self.min_w
            elif self.min_ff<=0:
                w = self.min_w
            else:
                w = self.max_w
            for x in self.pause( w ):
                self.__auto( True )
                yield True
            for x in self.until(lambda: self.closed, min=3000,step='pulse.low'):
                self.__auto( False )
                yield True
    
    @sfcaction
    def main(self) :
        self.log(f'ready')
        self.busy = False
        while self.sfc_reset:
            self.err = 0
            self.out = False
            self.sfc_step = 'emergency'
            yield True
    
        for x in self.until( self.f_go ,step='ready'):
            self.busy = False
            self.ready= True
            yield x
        self.ready= False
        self.busy = True
        from_m = self.m 
        self.log(f'rought mode from {from_m}')
        for x in  self.__rought( self.sp ):
            yield x
        self.log(f'precise mode from {self.m:.1f}')
        for x in self.__precise( self.sp, from_m=from_m ):
            yield x
        self.log(f'stabilization {self.m:.1f}')
        for x in self.until(lambda: self.closed, min=2,max=2 ,step = 'stab'):
            yield x
        if self.sp>0:
            self.err = (self.m - (from_m + self.sp - (self.take if self.take>0 else 0)) ) 
            self.log(f'done, m={self.m:.2f}, err={(self.err)/self.sp*100:.1f}%')
        self.take = None
    
@sfc(inputs=['sp','go','closed','clk'],outputs=['out'],vars=['busy','e','done','err'],id='flowmeter')
class FlowMeter(SFC):
    def __init__(self, sp = 0.0, clk=False, go = False, closed=True) -> None:
        self.go = go
        self.sp = sp
        self.closed = closed
        self.out = False
        self.ready = True
        self.busy = False
        self.clk = clk
        self.complete = False   #pulse after acoplishing collect
        self.f_go = FTRIG(clk = lambda: self.go )
        self.e = 0.0    #maxium posible error
        self.err = 0.0  #accumulated error 
        self.done = 0.0 #amount inside dosator
        self.afterOut = TOF( id='afterOut', clk=lambda: self.out, pt=2000 )
        self.subtasks = [self.afterOut]
        self.__counter = None
        self.q = Flow( )

        self.subtasks = [self.__counting]

    def __counting(self):
        if self.__counter is None:
            return

        self.q( self.__counter.q.clk,self.__counter.q.m )
        self.__counter()
        self.done=self.__counter.e
    
    def remote(self,out=None):
        self.__auto(out)

    def __auto(self,out=None):
        if out is not None and not self.manual:
            self.out = out

    def install_counter(self,flow_out: callable = None):
        self.__counter = RotaryFlowMeter(clk=lambda: self.clk ,flow_in = self.afterOut.q ,rst = flow_out )
        #self.q = self.__counter.q
       
    def collect(self,sp=None):
        if sp:
            self.sp = sp
        if not self.ready:
            return
        self.ready = False
        self.f_go( clk = True )
        
    @sfcaction
    def main(self) :
        self.log(f'ready')
        self.busy = False
        while self.sfc_reset:
             yield True
        for x in self.until( self.f_go ):
            self.busy = False
            self.ready= True
            yield x
        self.ready= False
        self.busy = True
        from_m = self.done
        self.log(f'collecting from {from_m} up to {from_m+self.sp}')
        for x in  self.till( lambda: self.done<from_m + self.sp ):
            self.__auto( out = True)
            yield x
        for x in self.until( lambda: self.closed,min=2 ):
            self.__auto( out = False )
            yield x
        self.log(f'collecting complete at {self.done}')
        self.complete = True
        yield True
        self.complete = False

class Accelerator():
    def __init__(self, outs: list[callable], sts: list[callable] = [] ):
        self.en = True
        self.cnt = len(outs)  #сколько доступно затворов
        self.src = None       #основной бункер
        self.outs = outs      #все затворы в помощь  
        self.sts = sts        #обратная связь по затворам
        self.cur = 0          #номер затвора что сейчас открывается/будет открываться
        self.nxt = 0          #кто на очереди
        self.out = False      #выход в обычном режиме 
        self.closed = True    #состояние обобщенное
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
                    break
                
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
                self.cur = self.nxt
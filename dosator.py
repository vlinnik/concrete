from pyplc.sfc import *
from pyplc.utils.trig import FTRIG
from pyplc.utils.latch import RS
from pyplc.utils.misc import TOF
from .counting import MoveFlow,Flow,Counter

class ManualDosator(SFC):
    level = POU.input(False,hidden=True)
    loaded = POU.input(False,hidden=True)
    closed = POU.input(False,hidden=True)
    load = POU.output(False,hidden=True)
    lock = POU.input(False)
    out = POU.output(False)
    full = POU.output(False)
    helper = POU.output(False)
    unloadT = POU.var(0,persistent=True)
    
    def __init__(self,level:bool = False, closed:bool=True,out:bool=False, lock:bool=False,full: bool = False, helper: bool = False, dosator:'Dosator' = None, id:str=None,parent:POU=None) -> None:
        super().__init__( id,parent )
        self.helper_t = 5
        self.closed = closed
        self.out = out
        self.lock = lock
        self.full = full
        self.helper = helper
        self.level = level
        self.go = False
        self.unload = False
        self.unloaded = False
        self.loaded = False
        self.manual = True
        self.ready = True
        self.count = 1
        self.delay = 2000
        self.s_go = RS(set = lambda: self.go,id = 's_go')
        self.s_unload = RS(set=lambda: self.unload, id = 's_unload')
        self.s_loaded = RS(set=lambda: self.loaded, id = 's_loaded' )
        self.dosator = dosator
        self.subtasks = [ self.s_go, self.s_unload, self.s_loaded]
        self.e = 0.0
        
        if dosator:
            self.join('loaded',lambda: dosator.unloaded )
            self.subtasks.append(self.__dosator)
            
            self.expenses=[ MoveFlow(flow_in=c.q, out=lambda: self.out) for c in dosator.containers ]
        else:
            self.expenses=[ ]
        
    def switch_mode(self,manual: bool ):
        self.log(f'ручной режим = {manual}')
        self.out = False
        self.manual = manual
    
    def emergency(self,value: bool = True):
        self.log(f'аварийный режим = {value}')
        self.go = False
        self.out = False
        self.unload = False
        self.s_loaded.unset( )
        self.s_unload.unset( )
        self.s_go.unset()
        self.sfc_reset = value
        self.out = False
        
    def __auto(self,out:bool = None):
        if out is not None and not self.manual:
            self.out = out and not self.lock
            
    def __dosator(self):
        if self.dosator:
            self.dosator.go = self.go
            self.dosator.count = self.count
            total = 0.0
            for e in self.expenses:
                e( )
                total+=e.e
            self.e = total
            
    def cycle( self ,batch:int=0):
        self.log(f'ждем загрузки..')
        self.load = True
        if self.dosator: self.dosator.unload = True
        yield
        self.load = False
        if self.dosator: self.dosator.unload = False
        yield from self.until( lambda: self.s_loaded.q, step='wait.loaded')
        self.full = True
        self.log(f'ждем выгрузки..')
        yield from self.until( lambda: self.s_unload.q, step='wait.unload')
        self.unload = False
        self.unloaded = False
        yield from self.pause(self.delay,step='delay')

        self.log(f'выгружаем {self.unloadT} сек')
        secs = 0 
        while secs<self.unloadT or self.level:
            self.__auto( True )
            yield from self.pause(1000,step='pause.1sec')
            secs+=1
            if secs+self.helper_t>self.unloadT:
                self.helper = True
            yield
        self.helper = False

        self.__auto( False )
        self.full = False
        yield from self.until( lambda: self.closed,min=3000, step='wait.closed' )
        self.s_loaded.unset( )
        self.s_unload.unset( )

        self.unloaded = True
        yield 
        self.unloaded =  False

    def main(self):
        self.log(f'готов')
                
        for _ in self.until( lambda: self.s_go.q , step='ready' ):
            self.ready=True
            yield

        self.s_go.unset( )
        self.ready=False
        count = self.count 
        batch = 0

        while batch<count:   
            yield from self.cycle(batch)

            batch = batch+1 
            count = self.count 
        
class Dosator(SFC):
    """Логика дозатора. Выполняет процедуру набора/выгрузки count раз. Выгрузка имеет задержку unloadT"""
    count = POU.input(0)
    go = POU.input(False)
    m = POU.input(0.0,hidden=True)
    closed = POU.input(False,hidden=True)
    lock = POU.input(False)
    out = POU.output(False)
    unloadT = POU.var(0,persistent=True)
    ignore = POU.var(0.0,persistent=True)
    fail = POU.var(False)
    compensation = POU.var(False)
    leave = POU.var(False)
    ack = POU.var(False)
    nack= POU.input(False,hidden=True)

    def __init__(self,m:float=0, closed:bool=True,out:bool=False, unloaded:bool=False,lock:bool=False,containers = (),id:str = None,parent:POU=None) -> None:
        super().__init__( id,parent )
        self.out = out
        self.unloaded=unloaded
        self.ignore = 0.0
        self.m = m 
        self.containers = containers
        self.closed = closed
        self.unload = False
        self.loaded = False
        self.ready = False
        self.fail = False
        self.manual = True
        self.lock = lock
        self.compensation = False
        self.leave = False
        self.ack = False
        self.nack= False    #механизм порядка загрузки
        self.s_go = RS(set = lambda: self.go,id = 's_go')
        self.s_unload = RS(set=lambda: self.unload, id = 's_unload')
        self.s_loaded = RS(set=lambda: self.loaded, id = 's_loaded' )
        self.t_ack = FTRIG(clk = lambda: self.ack )
        self.subtasks = ( self.always, )
        for c in self.containers:
            c.install_counter( flow_out = lambda: self.out ,m = lambda: self.m )
            
    def switch_mode(self,manual: bool ):
        self.log(f'ручной режим = {manual}')
        self.out = False
        self.manual = manual
        for c in self.containers:
            c.switch_mode(manual)
    
    def emergency(self,value: bool = True):
        self.log(f'аварийный режим = {value}')
        self.out = False
        self.go = False
        self.s_loaded.unset( )
        self.s_unload.unset( )
        self.s_go.unset()
        self.unload = False
        self.sfc_reset = value
        for c in self.containers:
            c.emergency(value)
            
    def __loading(self):
        result = False
        for c in self.containers:
            result = result or c.out
        return result

    def __auto(self,out=None):
        if out is not None and not self.manual:
            self.out = out and not self.lock

    def always(self):
        self.s_loaded( ) 
        self.s_unload( )
        self.s_go( )
        self.out = not self.lock and self.out 

    def start(self,count=None,unload=False):
        self.count = self.count if count is None else count
        if unload:
            self.s_unload(set=True)

        self.s_go( set = True )
        self.ready = False

    def is_loaded(self):
        return self.s_loaded.q

    def cycle( self ,batch=0):
        self.required = [c for c in filter(lambda c: c.sp>0, self.containers )]

        yield from self.until( lambda: all( [c.ready for c in self.required] ),step='wait.containers' )
            
        self.fail = False
        if len(self.required)>0: self.log(f'ждем окончания набора замеса #{batch+1}..')
        if self.m>self.ignore:
            fract = self.m
        else:
            fract = 0
        for c in self.required:
            if fract>c.sp:
                fract-=c.sp
            else:
                c.take = fract  #учесть как уже набранное
                fract = 0
                if self.compensation:
                    c.take += c.err
                else:
                    c.err = 0
                c.collect( )
                yield from self.until( lambda: c.ready or self.is_loaded(), step='collecting')
                if c.err>=c.max_sp*0.04:
                    self.fail = True
                    while not self.t_ack( ):
                        yield 
                    self.fail = False

        self.loaded = True
        yield 
        self.loaded = False

        if len(self.required)>0: self.log(f'ждем выгрузки..')
        yield from self.until( lambda: self.s_unload.q, step='wait.unload')
        self.unload = False
        self.unloaded = False
        if self.leave:
            rest = self.m  #посмотрим сколько нужно оставить в дозаторе
            for c in self.required:
                rest -= c.sp
            if rest<=self.ignore:
                rest = self.ignore
        else:
            rest = self.ignore

        if len(self.required)>0:
            self.log(f'выгрузка через {self.unloadT} сек')
            secs = 0 
            yield from self.till(lambda: self.nack,step='till.nack')
            while secs<self.unloadT:
                yield from self.pause(1000,step='pause.1sec')
                secs+=1
                yield
            self.log(f'выгружаем..')
            yield from self.till( lambda: self.m>self.ignore and self.m>rest, step='unloading',n = [self.__auto] )
            yield from self.until( lambda: self.closed,min=3000, step='wait.closed' )
            if self.compensation and self.leave and self.m>self.ignore: #скорректируем ошибку дозирования на то что удалось оставить в дозаторе
                rest = self.m
                for c in self.required:
                    if rest>c.err:
                        rest-=c.err
                        c.err = 0
                    else:
                        c.err -= rest
                        rest = 0


        self.s_loaded.unset( )
        self.s_unload.unset( )

        self.unloaded = True
        yield 
        self.unloaded =  False
        self.log('выгрузка завершена')

    def main(self):
        self.log(f'готов')
                
        for _ in self.until( lambda: self.s_go.q , step='ready' ):
            self.ready=True
            yield

        self.s_go.unset( )
        self.ready=False
        count = self.count 
        batch = 0
        
        while batch<count:   
            yield from self.cycle(batch)

            batch = batch+1 
            count = self.count 

class DescendingDosator(Dosator):
    """Логика дозатора. Выполняет процедуру дозирования на убывание count раз. Дозирование имеет задержку unloadT сек"""
    full = POU.var(10.0,persistent=True) 
    low  = POU.var(0.0,persistent=True)
    clear= POU.input(False,hidden=True)
    done = POU.var(0.0)
    busy = POU.var(False)
    
    def __init__(self,m:float=0, closed:bool=True,out:bool=False,lock:bool=False,containers = (),id:str = None,parent:POU=None) -> None:
        super().__init__(m=m,closed=closed,out=out,containers=containers, lock=lock, id=id, parent=parent)
        self.autotune = False
        self.afterOut = TOF( id='afterOut', clk=lambda: self.out, pt=3000 )
        self.__counter = Counter(m = lambda: -self.m ,flow_in = lambda: self.afterOut.q,flow_out = lambda: not self.afterOut.q)
        self.q = self.__counter.q
        self._done = 0.0
        self.subtasks += (self.afterOut,self.__counter,self.__counting)

    def __counting(self):
        self.done = self._done + self.__counter.live
        if self.clear: 
            self._done = 0
            self.__counter.live = 0
        if not self.afterOut.q and self.out:
            self._done = self.done
        
    def map(self,clear:bool=None):
        if clear is not None: self.join('clear',clear)
                
    def wait(self,sec:int):
        while sec>0:
            yield from self.pause(1000)
            sec-=1

    def __auto(self,out=None):
        if out is not None and not self.manual:
            self.out = out and not self.lock

    def __rought(self, c: 'Container' , from_m: float):
        self.log(f'грубый режим с {self.m} кг')
        yield from self.till( lambda: self.m>from_m-c.sp+c.min_ff,step='rought',n=(self.__auto,))
        yield from self.until( lambda: self.closed,min=3000 ,step = 'after.rought')

    def __precise(self,c: 'Container', from_m: float):
        self.log(f'точный режим с {self.m} кг')
        while self.m>from_m-c.sp*0.99+c.e:
            dm = c.sp-(from_m - self.m)
            if c.min_ff>0 and dm<=c.min_ff:
                w = dm/c.min_ff*(c.max_w-c.min_w)+c.min_w
            elif c.min_ff<=0:
                w = c.min_w
            else:
                w = c.max_w
            yield from self.pause( w,n=(self.__auto,) )
            yield from self.until(lambda: self.closed, min=3000,step='pulse.low')
        
    def cycle( self,batch:int=0):
        self.required = tuple(c for c in filter(lambda c: c.sp>0, self.containers ))
        required_weight = 0
        if len(self.required)>0: 
            yield from self.until( lambda: all( tuple(c.ready for c in self.required) ),step='wait.containers' ) 
            required_weight = sum( (c.sp for c in self.required) )

            if self.m<required_weight or self.m<self.low:
                self.log(f'в дозаторе недостаточно для цикла дозирования. пополняем...')
                for _ in self.till(lambda: self.m<self.full):
                    if not self.manual:
                        for c in self.required:
                            c.out = True
                    yield _
                for c in self.required:
                    c.out = False
                yield from self.wait(3)

        self.loaded = True
        yield 
        self.loaded = False
            
        self.log(f'ждем комманды выгружаться..')
        yield from self.until( lambda: self.s_unload.q, step='wait.unload')
        self.unload = False
        self.s_unload.unset( )

        if required_weight>0:
            self.log(f'начало выгрузки через {self.unloadT} сек')
            yield from self.wait( self.unloadT )
            
            self.fail = False
            self.busy = True
            # ждем окончания дозирования выгрузкой
            for c in self.required:
                from_m = self.m
                if self.compensation:
                    from_m+=c.err
                yield from self.__rought(c,from_m)
                yield from self.__precise(c,from_m)
                c.err  = (from_m - self.m) - c.sp
            self.busy = False

        self.unloaded = True
        yield True
        self.unloaded =  False

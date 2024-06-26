from pyplc.sfc import *
from pyplc.utils.trig import FTRIG
from pyplc.utils.latch import RS

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
    @POU.init
    def __init__(self,m=0, closed:bool=True,count:int=1,go:bool=False,loaded:bool=False,unload:bool=False,out:bool=False, unloaded:bool=False,unloadT:int=0,lock:bool=False,nack:bool=False,containers = []) -> None:
        super().__init__( )
        self.count = count
        self.go = go
        self.unload = unload
        self.out = out
        self.unloaded=unloaded
        self.loaded = loaded
        self.unloadT = unloadT
        self.ignore = 0.0
        self.m = m 
        self.containers = containers
        self.closed = closed
        self.ready = False
        self.fail = False
        self.manual = True
        self.lock = lock
        self.compensation = False
        self.leave = False
        self.ack = False
        self.nack= nack    #механизм порядка загрузки
        self.s_go = RS(set = lambda: self.go,id = 's_go')
        self.s_unload = RS(set=lambda: self.unload, id = 's_unload')
        self.s_loaded = RS(set=lambda: self.loaded, id = 's_loaded' )
        self.t_ack = FTRIG(clk = lambda: self.ack )
        self.subtasks = [ self.always ]
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
        self.s_loaded.unset( )
        self.s_unload.unset( )
        self.s_go.unset()
        self.sfc_reset = value
        self.out = False
        self.s_loaded.unset( )
        self.s_unload.unset( )
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

class DescendingDosator(SFC):
    """Логика дозатора. Выполняет процедуру дозирования на убывание count раз. Дозирование имеет задержку unloadT сек"""
    count = POU.input(0)
    go = POU.input(False)
    m = POU.input(0.0,hidden=True)
    lock = POU.input(False)
    unloadT = POU.var(0,persistent=True)
    fail = POU.var(False)
    compensation = POU.var(False)
    ack = POU.var(False)
    @POU.init
    def __init__(self,m=0, count=1,go=False,unload=False,unloaded=False,unloadT=0,lock=False,containers = []) -> None:
        super().__init__( )
        self.count = count
        self.go = go
        self.unload = unload
        self.unloaded=unloaded
        self.unloadT = unloadT
        self.ignore = 0.0
        self.m = m 
        self.containers = containers
        self.ready = False
        self.fail = False
        self.manual = True
        self.lock = lock
        self.compensation = False
        self.ack = False
        self.s_go = RS(set = lambda: self.go,id = 's_go')
        self.s_unload = RS(set=lambda: self.unload, id = 's_unload')
        self.t_ack = FTRIG(clk = lambda: self.ack )
        for c in self.containers:
            c.install_counter( flow_out = lambda: self.unloaded ,m = lambda: -self.m )
        self.subtasks = [ self.always ]
            
    def switch_mode(self,manual: bool ):
        self.log(f'toggled manual = {manual}')
        self.manual = manual
    
    def emergency(self,value: bool = True):
        self.log(f'emergency = {value}')
        self.out = False
        self.s_unload.unset( )
        self.s_go.unset()
        self.sfc_reset = value
        self.s_unload.unset( )
            
    def always(self):
        self.s_unload( )
        self.s_go( )

    def start(self,count=None,unload=False):
        self.count = self.count if count is None else count
        if unload:
            self.s_unload(set=True)

        self.s_go( set = True )
        self.ready = False

    def cycle( self ,batch=0):
        self.required = [c for c in filter(lambda c: c.sp>0, self.containers )]
        self.log(f'wait for required containers get ready..')
        for x in self.until( lambda: all( [c.ready for c in self.required] ),step='wait.containers' ):
            yield x
            
        self.log(f'waiting for unload..')
        for x in self.until( lambda: self.s_unload.q, step='wait.unload'):
            yield x
        self.unload = False

        self.log(f'unloading after {self.unloadT} sec')
        for x in self.pause( self.unloadT*1000 , step='pause.unload' ):
            yield x

        self.fail = False
        self.log(f'waiting for get loaded #{batch+1}..')
        for c in self.required:
            c.take = 0
            if self.compensation:
                c.take += c.err
            else:
                c.err = 0
            c.collect( )
            for x in self.until( lambda: c.ready, step='collecting'):
                yield x
            if c.err>=c.max_sp*0.04:
                self.fail = True
                while not self.t_ack( ):
                    yield True
                self.fail = False
        
        self.s_unload.unset( )

        self.log(f'pause for ui 1 sec')
        for x in self.pause( 1000 , step='pause.afterUnload' ):
            yield x

        self.unloaded = True
        yield True
        self.unloaded =  False

    
    @sfcaction
    def main(self):
        self.log(f'ready')
                
        for x in self.until( lambda: self.s_go.q , step='ready' ):
            self.ready=True
            yield True

        self.s_go.unset( )
        self.ready=False
        count = self.count 
        self.log(f'starting dose/unload cycle #{count} times')
        batch = 0
        
        while batch<count and not self.sfc_reset:   
            for x in self.cycle(batch):
                yield x

            batch = batch+1 
            count = self.count 
            self.log(f'finished {batch}/{count}')

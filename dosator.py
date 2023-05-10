from pyplc.sfc import *
from pyplc.utils.trig import RTRIG
from pyplc.utils.latch import RS
import time

class Lock():
    def __init__(self,delay: float = 3, key: callable = None):
        self.delay = int(delay*1000000000)
        self.q = False
        self._x = None
        self._key = key
        
    def __call__(self, key: bool=None) -> bool:
        if callable(self._key)  and key is None:
            key = self._key( )
            
        if key:
            self.q = True
            self._x = time.time_ns()
        elif self._x is not None:
            self.q = (time.time_ns() - self._x)<self.delay
        else:
            self.q = False
            
        return self.q

@sfc(inputs=['count','go','m','closed','lock'],outputs=['out'],vars=['unloadT','ignore','fail','compensation'])
class Dosator(SFC):
    """Логика дозатора. Выполняет процедуру набора/выгрузки count раз. Выгрузка имеет задержку unloadT
    """
    def __init__(self,m=0, closed=True,count=1,go=False,loaded=False,unload=False,out=False,unloaded=False,unloadT=0,lock=False,containers = []) -> None:
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
        self.fast = False
        self.t_go = RTRIG(clk = lambda: self.go,id = 't_go')
        self.s_unload = RS(set=lambda: self.unload, id = 's_unload')
        self.s_loaded = RS(set=lambda: self.loaded, id = 's_loaded' )
        self.out_forbidden = Lock(key = self.__loading )
        self.subtasks = [ self.always ]
        for c in self.containers:
            c.install_counter( flow_out = lambda: self.out )
            
    def switch_mode(self,manual: bool ):
        self.log(f'toggled manual = {manual}')
        self.out = False
        self.manual = manual
    
    def emergency(self,value: bool = True):
        self.log(f'emergency = {value}')
        self.sfc_reset = value
            
    def __loading(self):
        result = False
        for c in self.containers:
            result = result or c.out
        return result

    def __auto(self,out=None):
        if out is not None and not self.manual:
            self.out = out
   
    def always(self):
        self.fast = False
        for c in self.containers:
            c.lock = self.out
            self.fast = self.fast or c.fast
            
        self.s_loaded( ) 
        self.s_unload( )
        self.t_go( )
        self.out = not self.lock and not self.out_forbidden() and self.out 

    def start(self,count=None,unload=False):
        self.count = self.count if count is None else count
        if unload:
            self.s_unload(set=True)

        self.t_go( clk = True )
        self.ready = False

    def is_loaded(self):
        return self.s_loaded.q

    def cycle( self ,batch=0):
        self.required = [c for c in filter(lambda c: c.sp>0, self.containers )]
        self.log(f'wait for required containers get ready..')
        for x in self.until( lambda: all( [c.ready for c in self.required] ),step='wait.containers' ):
            yield x

        self.log(f'waiting for get loaded #{batch+1}..')
        fract = self.m
        for c in self.required:
            if fract>c.sp:
                fract-=c.sp
            else:
                c.take = fract  #учесть как уже набранное
                if self.compensation:
                    c.take += c.err
                else:
                    c.err = 0
                c.collect( )
                for x in self.until( lambda: c.ready or self.is_loaded(), step='collecting'):
                    yield x

        self.loaded = True
        yield True
        self.loaded = False

        self.log(f'waiting for unload..')
        for x in self.until( lambda: self.s_unload.q, step='wait.unload'):
            yield x
        self.unload = False
        self.unloaded = False

        self.log(f'unloading after {self.unloadT} sec')
        for x in self.pause( self.unloadT*1000 , step='pause.unload' ):
            yield x

        if len(self.required)>0:
            self.log(f'unloading..')
            for x in self.till( lambda: self.m>self.ignore, step='unloading' ):
                self.__auto( out = True )
                yield True

            self.__auto(out = False)
            for x in self.until( lambda: self.closed,min=3000, step='wait.closed' ):
                yield True

        self.s_loaded.unset( )
        self.s_unload.unset( )

        self.unloaded = True
        yield True
        self.unloaded =  False
    
    @sfcaction
    def main(self):
        self.log(f'ready')
        
        while self.sfc_reset:
            self.sfc_step = 'emergency'
            self.out = False
            self.s_loaded.unset( )
            self.s_unload.unset( )
            yield True
        
        for x in self.until( lambda: self.t_go.q , step='ready' ):
            self.ready=True
            yield True

        self.ready=False
        count = self.count 
        self.log(f'starting dose/unload cycle #{count} times')
        batch = 0
        
        for c in [c for c in filter(lambda c: c.sp>0, self.containers )]:
            c.err = 0 
            
        while batch<count and not self.sfc_reset:   
            for x in self.cycle(batch):
                yield x

            batch = batch+1 
            count = self.count 
            self.log(f'finished {batch}/{count}')

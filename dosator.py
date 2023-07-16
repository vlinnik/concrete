from pyplc.sfc import *
from pyplc.utils.trig import FTRIG
from pyplc.utils.latch import RS
import time

@sfc(inputs=['count','go','m','closed','lock'],outputs=['out','fast'],vars=['unloadT','ignore','fail','compensation','leave','ack'],hidden=['m','closed','fast'],persistent=['unloadT','ignore'])
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
        self.leave = False
        self.ack = False
        self.s_go = RS(set = lambda: self.go,id = 's_go')
        self.s_unload = RS(set=lambda: self.unload, id = 's_unload')
        self.s_loaded = RS(set=lambda: self.loaded, id = 's_loaded' )
        self.t_ack = FTRIG(clk = lambda: self.ack )
        self.subtasks = [ self.always ]
        for c in self.containers:
            c.install_counter( flow_out = lambda: self.out ,m = lambda: self.m )
            
    def switch_mode(self,manual: bool ):
        self.log(f'toggled manual = {manual}')
        self.out = False
        self.manual = manual
    
    def emergency(self,value: bool = True):
        self.log(f'emergency = {value}')
        self.out = False
        self.s_loaded.unset( )
        self.s_unload.unset( )
        self.s_go.unset()
        self.sfc_reset = value
            
    def __loading(self):
        result = False
        for c in self.containers:
            result = result or c.out
        return result

    def __auto(self,out=None):
        if out is not None and not self.manual:
            self.out = out and not self.lock
   
    def always(self):
        self.fast = self.out
        for c in self.containers:
            self.fast = self.fast or c.fast or (c.out and not c.busy) 
            
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
        self.log(f'wait for required containers get ready..')
        for x in self.until( lambda: all( [c.ready for c in self.required] ),step='wait.containers' ):
            yield x
            
        self.fail = False
        self.log(f'waiting for get loaded #{batch+1}..')
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
                for x in self.until( lambda: c.ready or self.is_loaded(), step='collecting'):
                    yield x
                if c.err>=c.max_sp*0.04:
                    self.fail = True
                    while not self.t_ack( ):
                        yield True
                    self.fail = False

        self.loaded = True
        yield True
        self.loaded = False

        self.log(f'waiting for unload..')
        for x in self.until( lambda: self.s_unload.q, step='wait.unload'):
            yield x
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

        self.log(f'unloading after {self.unloadT} sec')
        for x in self.pause( self.unloadT*1000 , step='pause.unload' ):
            yield x

        if len(self.required)>0:
            self.log(f'unloading..')
            for x in self.till( lambda: self.m>self.ignore and self.m>rest, step='unloading' ):
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

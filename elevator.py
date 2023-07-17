from pyplc.sfc import *
from pyplc.utils.trig import FTRIG
from pyplc.utils.latch import RS

from concrete.container import Container
from .counting import MoveFlow

@sfc(inputs=['above','below','middle','loaded','go','count','lock'],outputs=['up','down'],vars=['maxT','fault','ack','moveT','unloadT','pauseT','manual','state'],persistent=['maxT','moveT','pauseT','unloadT'],hidden=['loaded','go','count'])
class ElevatorGeneric(SFC):
    def __init__(self,above=False,below=False,middle =False, loaded = False,containers:list[Container]=[],lock = False ):
        self.lock = False
        self.filled = 0.0
        self.above = above
        self.below = below
        self.middle = middle
        self.moveT = 0
        self.maxT = 30
        self.pauseT = 3
        self.unloadT = 10
        self.manual = False
        self.__manual = False
        self.__finalizing = False
        self.fault = False
        self.ack = False
        self.load = False
        self.loaded = loaded
        self.unload = False
        self.unloaded = False
        self.unloading = False
        self.count = 1
        self.go = False
        self.up = False
        self.down = False
        self.dir = 0        #куда ехать. 0 - стоим 1 - вверх до конца 1 - вниз до конца
        self.state = 'СВОБОДЕН'
        self.flows = [ MoveFlow( flow_in = c.q ,out = lambda: self.above) for c in containers ]
        self.f_go = FTRIG(clk=lambda: self.go )
        self.s_loaded = RS(set=lambda: self.loaded)
        self.s_unload = RS(set=lambda: self.unload)
        self.subtasks=[self.s_loaded,self.s_unload,self.f_go,self.always] + self.flows
    
    def always(self):
        if self.lock:
            self.up = False
            self.down = False
            
    def switch_mode(self,manual: bool ):
        self.log(f'toggled manual = {manual}')
        self.up = False
        self.down = False

    def emergency(self,value: bool = True):
        self.log(f'emergency = {value}')
        self.up = False
        self.down = False
        self.s_loaded.unset()
        self.s_unload.unset()
        self.sfc_reset = value

    def __auto(self,up=None,down=None):
        if self.manual!=self.__manual and self.manual:
            self.up = False
            self.down = False
            self.dir = 0            
        elif not self.manual:
            if self.dir!=0:
                up = self.dir>0 and not self.above 
                down = self.dir<0 and not self.below
                if self.below and self.dir<0:
                    self.dir = 0
                if self.above and self.dir>0:
                    self.dir = 0
            if up is not None:
                self.up = up and not self.above 
            if down is not None:
                self.down = down and not self.below 
        self.__manual = self.manual

    def start( self,count = 1 ):
        self.log(f'starting {count} cycles')
        self.f_go(clk=True)
        self.count = count
    
    def __fail(self,msg: str):
        self.log(msg)
        self.fault = True
        self.__auto(up=False,down=False)
        for x in self.until(lambda: self.ack):
            yield x
        self.fault = False
    
    def move(self,dir: int):
        if self.dir!=0:
            return
        self.dir = dir
        
    @sfcaction
    def collect( self ,batch=0):
        self.state = f'ЗАГРУЗКА #{batch+1}'
        self.log(f'waiting for get loaded #{batch+1}..')
        self.load = True
        yield True
        yield True
        self.load = False
        for x in self.until(lambda: self.s_loaded.q,step='wait loaded'):
            yield x
        self.filled += sum( [f.e for f in self.flows] )
            
    @sfcaction
    def main(self) :
        self.log('ready')

        if self.__finalizing:
            self.state = 'ДОМОЙ'
            for x in self.until( lambda: self.f_go.q or self.below ,max = self.maxT*1000, step = 'ready&back'):
                yield x
                self.__auto(up=False,down=not self.below)
            self.__finalizing = False
                
        self.state = 'ГОТОВ'
        for x in self.until( lambda: self.f_go.q , step = 'ready'):
            self.__auto(up=False,down=False)
            yield x
        
        self.state = 'НА ПОГРУЗКУ'
        while not self.below:
            for x in self.until( lambda: self.below,max=self.maxT*1000, step='return'):
                yield x
                self.__auto(up=False,down=True)
            self.__auto(up=False,down=False)
            if not self.below:
                for x in self.__fail('fault during moving down'):
                    yield x
        batch = 0
        count = self.count
        while batch<count:
            while not self.below:
                self.log('moving down')
                self.state = 'ВОЗВРАТ'
                for x in self.until(lambda: self.below and not self.above,max=self.maxT*1000,step = 'back'):
                    yield x
                    self.__auto(up=False,down=True)
                if not self.below:
                    for x in self.__fail('fault during moving down'):
                        yield x
            for x in self.pause(self.pauseT*1000,step='pause'):
                yield x

            for x in self.exec(self.collect(batch)).wait:
                yield x
            
            self.log('loaded. pause and move closer')
            self.state = f'ПАУЗА {self.pauseT} СЕК'
            for x in self.pause(self.pauseT*1000, step='pause'):
                yield x
            
            if self.moveT>0:
                self.state = 'ПОБЛИЖЕ...'
                for x in self.until(lambda: self.middle,max = self.moveT*1000 , step='closer'):
                    yield x
                    self.__auto(up=True,down=False)
                if not self.middle:
                    self.middle = True

            self.log('waiting for unload signal')
            self.state = f'ЖДЕМ ВЫГРУЗКИ #{batch+1}'
            for x in self.until(self.s_unload, step = 'steady'):
                self.__auto(up = False,down=False)
                yield x

            self.state = f'НА ВЫГРУЗКУ #{batch+1}'
            self.unload = False
            self.s_unload.unset()
            self.log('moving up')
            while not self.above:
                for x in self.until(lambda: self.above,max=self.maxT*1000, step = 'go!'):
                    yield x
                    self.__auto(up=True,down=False)
                if not self.above:
                    for x in self.__fail('fault during moving up'):
                        yield x

            self.state = f'ВЫГРУЗКА #{batch+1}'
            self.log('unloading')
            self.filled = 0.0
            if self.middle:
                self.middle = False
            self.unloading = True
            for i in self.pause(self.unloadT*1000, step='unloading'):
                yield i
            self.unloading = False

            if not self.go:
                count = self.count
            self.loaded = False
            self.s_loaded.unset()
            self.unloaded = True
            yield True
            self.unloaded = False
            batch+=1
            self.log(f'batch {batch}/{count} finished')
        self.__finalizing = not self.sfc_reset

@sfc(inputs=['m','above','below','middle'],outputs=['up','down'],vars=['maxT','fault','ack','moveT','unloadT','pauseT','manual','state','ignore'],persistent=['maxT','moveT','pauseT','unloadT'])
class Elevator(SFC):
    def __init__(self,ignore: float = 30, m: float=0,above=False,below=False,middle =False, containers: list[Container]=[]):
        self.ignore = ignore
        self.compensation = False
        self.m = m
        self.above = above
        self.below = below
        self.middle = middle
        self.moveT = 0
        self.maxT = 30
        self.pauseT = 3
        self.unloadT = 10
        self.manual = False
        self.__manual = False
        self.__finalizing = False
        self.fault = False
        self.ack = False
        self.load = False
        self.loaded = False
        self.unload = False
        self.unloaded = False
        self.unloading = False
        self.count = 1
        self.go = False
        self.up = False
        self.down = False
        self.dir = 0        #куда ехать. 0 - стоим 1 - вверх до конца 1 - вниз до конца
        self.state = 'СВОБОДЕН'
        self.containers = containers
        self.f_go = FTRIG(clk=lambda: self.go )
        self.s_loaded = RS(set=lambda: self.loaded)
        self.s_unload = RS(set=lambda: self.unload)
        self.subtasks=[self.s_loaded,self.s_unload,self.f_go]
        for c in self.containers:
            c.install_counter( flow_out = lambda: self.above )

    def emergency(self,value: bool = True):
        self.log(f'emergency = {value}')
        self.sfc_reset = value

    def __auto(self,up=None,down=None):
        if self.manual!=self.__manual and self.manual:
            self.up = False
            self.down = False
            self.dir = 0            
        elif not self.manual:
            if self.dir!=0:
                up = self.dir>0 and not self.above
                down = self.dir<0 and not self.below
                if self.below and self.dir<0:
                    self.dir = 0
                if self.above and self.dir>0:
                    self.dir = 0
            if up is not None:
                self.up = up and not self.above
            if down is not None:
                self.down = down and not self.below
        self.__manual = self.manual

    def start( self,count = 1 ):
        self.log(f'starting {count} cycles')
        self.f_go(clk=True)
        self.count = count
    
    def __fail(self,msg: str):
        self.log(msg)
        self.fault = True
        self.__auto(up=False,down=False)
        for x in self.until(lambda: self.ack):
            yield x
        self.fault = False
    
    def move(self,dir: int):
        if self.dir!=0:
            return
        self.dir = dir
        
    def collect( self ,batch=0):
        self.required = [c for c in filter(lambda c: c.sp>0, self.containers )]
        self.log(f'wait for required containers get ready..')
        for x in self.until( lambda: all( [c.ready for c in self.required] ),step='wait.containers' ):
            yield x

        self.log(f'waiting for get loaded #{batch+1}..')
        fract = self.m if self.m>self.ignore else 0
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
                for x in self.until( lambda: c.ready, step='collecting'):
                    yield x

        self.loaded = True
        yield True
        self.loaded = False
            
    @sfcaction
    def main(self) :
        self.log('ready')
        while self.sfc_reset:
            self.state = 'СБРОС'
            self.s_unload.unset()
            self.s_loaded.unset()
            yield True

        if self.__finalizing:
            self.state = 'ДОМОЙ'
            for x in self.until( lambda: self.f_go.q or self.below ,max = self.maxT*1000, step = 'ready&back'):
                yield x
                self.__auto(up=False,down=not self.below)
            self.__finalizing = False
                
        self.state = 'ГОТОВ'            
        for x in self.until( lambda: self.f_go.q , step = 'ready'):
            self.__auto(up=False,down=False)
            yield x
        
        self.state = 'НА ПОГРУЗКУ'
        while not self.below and not self.sfc_reset:
            for x in self.until( lambda: self.below,max=self.maxT*1000, step='return'):
                yield x
                self.__auto(up=False,down=True)
            self.__auto(up=False,down=False)
            if not self.below:
                for x in self.__fail('fault during moving down'):
                    yield x
        batch = 0
        count = self.count
        while batch<count and not self.sfc_reset:
            while not self.below and not self.sfc_reset:
                self.log('moving down')
                self.state = 'ВОЗВРАТ'
                for x in self.until(lambda: self.below and not self.above,max=self.maxT*1000,step = 'back'):
                    yield x
                    self.__auto(up=False,down=True)
                if not self.below:
                    for x in self.__fail('fault during moving down'):
                        yield x
            for x in self.pause(self.pauseT*1000,step='pause'):
                yield x

            self.log('loading')
            self.load = True
            yield True
            self.load = False
            for x in self.collect(batch):
                self.state = f'ПОГРУЗКА #{batch+1}'
                yield x
            
            self.log('loaded. pause and move closer')
            self.state = f'ПАУЗА {self.pauseT} СЕК'
            for x in self.pause(self.pauseT*1000, step='pause'):
                yield x
            
            if self.moveT>0:
                self.state = 'ПОБЛИЖЕ...'
                for x in self.until(lambda: self.middle,max = self.moveT*1000 , step='closer'):
                    yield x
                    self.__auto(up=True,down=False)
                if not self.middle:
                    self.middle = True

            self.log('waiting for unload signal')
            self.state = f'ЖДЕМ ВЫГРУЗКИ #{batch+1}'
            for x in self.until(self.s_unload, step = 'steady'):
                self.__auto(up = False,down=False)
                yield x

            self.state = f'НА ВЫГРУЗКУ #{batch+1}'
            self.unload = False
            self.s_unload.unset()
            self.log('moving up')
            while not self.above and not self.sfc_reset:
                for x in self.until(lambda: self.above,max=self.maxT*1000, step = 'go!'):
                    yield x
                    self.__auto(up=True,down=False)
                if not self.above:
                    for x in self.__fail('fault during moving up'):
                        yield x

            self.state = f'ВЫГРУЗКА #{batch+1}'
            self.log('unloading')
            if self.middle:
                self.middle = False
            self.unloading = True
            for i in self.pause(self.unloadT*1000, step='unloading'):
                yield i
            self.unloading = False

            if not self.go:
                count = self.count
            self.loaded = False
            self.s_loaded.unset()
            self.unloaded = True
            yield True
            self.unloaded = False
            batch+=1
            self.log(f'batch {batch}/{count} finished')
        self.__finalizing = not self.sfc_reset
        

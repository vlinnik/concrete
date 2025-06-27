from pyplc.sfc import *
from pyplc.utils.trig import FTRIG
from pyplc.utils.latch import RS

from concrete.container import Container
from concrete.dosator import Dosator
from concrete.counting import MoveFlow

class ElevatorGeneric(SFC):
    """Логика скипа, загружается из другого дозатора
    """
    above = POU.input(False,hidden=True)
    below = POU.input(False,hidden=True)
    up = POU.output(False)
    down= POU.output(False)
    fault=POU.var(False)
    ack = POU.var(False)
    manual = POU.var(False)
    moveT = POU.var(20,persistent=True)
    pauseT = POU.var(3,persistent=True)
    unloadT = POU.var(10,persistent=True)
    maxT = POU.var(30,persistent=True)
    loaded = POU.input(False,hidden=True)
    weight = POU.var(0.0)
    state=POU.var('ГОТОВ')

    def __init__(self,above:bool=False,below:bool=False,middle:bool =False,up:bool=False, down:bool=False, containers: list[Container]=[], dosator: Dosator=None, id:str=None,parent: POU=None):
        super().__init__( id,parent)
        self.ready = False
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
        self.up = up
        self.down = down
        self.dir = 0        #куда ехать. 0 - стоим 1 - вверх до конца 1 - вниз до конца
        self.state = 'СВОБОДЕН'
        self.containers = containers
        self.dosator = dosator
        self.s_go = RS(set=lambda: self.go )
        self.s_loaded = RS(set=lambda: self.loaded)
        self.s_unload = RS(set=lambda: self.unload)
        self.subtasks=[self.s_loaded,self.s_unload,self.s_go,self.__always]
        if len(containers)>0 and dosator is not None:
            self.expenses=[ MoveFlow(flow_in=c.q, out=lambda: self.above) for c in containers ]
        else:
            self.expenses=[ ]


    def emergency(self,value: bool = True):
        self.log(f'режим аварии = {value}')
        self.sfc_reset = value
        self.up = False
        self.down = False
        self.dir = 0
        self.__finalizing = False
        self.unloading = False
        self.s_unload.unset()
        self.s_loaded.unset()
        self.s_go.unset()

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
        self.log(f'запуск {count} циклов')
        self.s_go(set=True)
        self.count = count
    
    def __fail(self,msg: str):
        self.log(msg)
        self.fault = True
        self.__auto(up=False,down=False)
        yield from self.until(lambda: self.ack)
        self.fault = False
    
    def move(self,dir: int):
        if self.dir!=0:
            return
        self.dir = dir

    def __always(self):
        if self.dosator is not None:
            self.dosator.go = self.go
            self.loaded = self.dosator.unloaded
            self.dosator.unload = self.load

        weight = 0.0
        for e in self.expenses:
            e( )
            weight += e.q.m
        self.weight = weight
        
    def collect( self ,batch=0):
        self.log(f'ждем загрузки #{batch+1}..')
        self.load = True
        yield
        self.load = False
        self.state = 'ЗАГРУЗКА'
        yield from self.until( lambda: self.s_loaded.q )
            
    def main(self) :
        self.log('готов')

        if self.__finalizing:
            self.state = 'ДОМОЙ'
            for _ in self.until( lambda: self.s_go.q or self.below ,max = self.maxT*1000, step = 'ready&back'):
                yield
                self.__auto(up=False,down=not self.below)
            self.__finalizing = False

        self.state = 'ГОТОВ'            
        self.ready = True
        for _ in self.until( lambda: self.s_go.q , step = 'ready'):
            self.__auto(up=False,down=False)
            yield
        
        self.ready = False
        yield from self.till( lambda: self.go, step='steady' )

        self.s_go.unset( )
        
        self.state = 'НА ПОГРУЗКУ'
        while not self.below and not self.sfc_reset:
            for _ in self.until( lambda: self.below,max=self.maxT*1000, step='return'):
                yield
                self.__auto(up=False,down=True)
            self.__auto(up=False,down=False)
            if not self.below:
                yield from self.__fail('fault during moving down')
        batch = 0
        count = self.count
        while batch<count:
            while not self.below:
                self.log('возврат вниз')
                self.state = 'ВОЗВРАТ'
                for _ in self.until(lambda: self.below and not self.above,max=self.maxT*1000,step = 'back'):
                    yield 
                    self.__auto(up=False,down=True)
                if not self.below:
                    yield from self.__fail('fault during moving down')

            yield from self.pause(self.pauseT*1000,step='pause')

            yield from self.collect(batch)
            
            self.log('загружен. пауза и поближе')
            self.state = f'ПАУЗА {self.pauseT} СЕК'
            yield from self.pause(self.pauseT*1000, step='pause')
            
            if self.moveT>0:
                self.state = 'ПОБЛИЖЕ...'
                for _ in self.until(lambda: self.middle,max = self.moveT*1000 , step='closer'):
                    yield
                    self.__auto(up=True,down=False)
                if not self.middle:
                    self.middle = True

            self.log('ждем сигнала выгрузки')
            self.state = f'ЖДЕМ ВЫГРУЗКИ'
            for _ in self.until(self.s_unload, step = 'steady'):
                self.__auto(up = False,down=False)
                yield

            self.state = f'НА ВЫГРУЗКУ'
            self.unload = False
            self.s_unload.unset()
            self.log('едем на выгрузку')
            while not self.above:
                for _ in self.until(lambda: self.above,max=self.maxT*1000, step = 'go!'):
                    yield
                    self.__auto(up=True,down=False)
                if not self.above:
                    yield from self.__fail('fault during moving up')

            self.state = f'ВЫГРУЗКА'
            self.log('выгрузка')
            if self.middle:
                self.middle = False
            self.unloading = True
            yield from self.pause(self.unloadT*1000, step='unloading')

            self.unloading = False

            if not self.go:
                count = self.count

            self.loaded = False
            self.s_loaded.unset()
            self.unloaded = True
            yield
            self.unloaded = False
            batch+=1
            self.log(f'замес {batch}/{count} завершен')
        self.__finalizing = True

class Elevator(ElevatorGeneric):
    m = POU.input(0.0,hidden=True)

    def __init__(self,ignore: float = 30, m: float=0,above:bool=False,below:bool=False,middle:bool =False,up:bool=False, down:bool=False, containers: list[Container]=[],id:str=None,parent: POU=None):
        super().__init__(above=above,below=below,middle =middle,up=up, down=down, containers=containers,id=id,parent=parent)
        self.ignore = ignore
        self.compensation = False
        self.m = m
        self.containers = containers
        for c in self.containers:
            c.install_counter( flow_out = lambda: self.above, m = m )
    
    def collect( self ,batch=0):
        self.required = [c for c in filter(lambda c: c.sp>0, self.containers )]
        self.log(f'ждем когда необходимые бункера освободятся..')
        yield from self.until( lambda: all( [c.ready for c in self.required] ),step='wait.containers' )

        self.log(f'ждем набора замеса #{batch+1}..')
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
                yield from self.until( lambda: c.ready, step='collecting')

        self.loaded = True
        yield True
        self.loaded = False

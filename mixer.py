from pyplc.sfc import *
from pyplc.utils.trig import RTRIG,FTRIG
from pyplc.utils.latch import RS
from .factory import Factory
from .counting import Flow,Expense

class Mixer(SFC):
    """Смеситель

    Args:
        go ( bool ) : запуск цикла работы
        gate ( MSGate ): управление затвором выгрузки
        loaded ( bool ): сигнал "смеситель загружен"
        load ( bool ): сигнал "можно загружать"
    """
    go = POU.input(False)
    count = POU.input( 0 )
    ready = POU.var(False)
    clock = POU.var( 0 )
    state = POU.var( 'ПОДКЛЮЧЕНИЕ' )
    mixT = POU.var(20)
    unloadT = POU.var(20)
    qreset = POU.var(False)
    ack = POU.var(False)
    req = POU.var(False)
    nack = POU.var(False)
    forbid = POU.var(False)
    breakpoint = POU.var(False)
    def __init__(self, count=1,gate=None, motor=None, go=False, loaded=False, load = False, factory:Factory = None, flows : list[Flow]=None, use_ack: bool = True ,id:str=None,parent:POU=None):
        super().__init__( id,parent)
        self.gate = gate
        self.motor = motor
        self.count = count
        self.mixT = 15
        self.unloadT = 15
        self.go = go
        self.loaded = loaded
        self.load = load
        self.loading = False
        self.ready = True
        self.ack = False
        self.nack = False
        self.req = True
        self.forbid = False
        self.breakpoint = False
        self.clock = 0
        self.state = 'СВОБОДНА'
        self.f_go = RTRIG( clk = lambda: self.go , id = 'f_go')
        self.f_ack = FTRIG( clk = lambda: self.ack, id= 'f_ack')
        self.f_nack = FTRIG( clk = lambda: self.nack)
        self.f_loaded = RS( set = lambda: self.loaded, id = 'f_loaded' )
        self.factory = factory
        self.qreset = False
        self.use_ack = use_ack
        if flows is not None:
            self.expenses=[ Expense( flow_in = f ,out = lambda: self.qreset ) for f in flows ]
            for i in range(0,len(flows)):
                self.export(f'expense_{i}',0.0)
        else:
            self.expenses=[ ]

        self.subtasks = [self.f_loaded,self.__counting,self.__always,self.f_go,self.f_ack,self.f_nack]
    
    def timer(self,preset: int, up: bool = True):
        """Отсчет времени и обновление свойства clock

        Args:
            preset (int): сколько секунд
            up (bool, optional): обратный или прямой отсчет. Defaults to True (прямой).

        Yields:
            True: не используется
        """        
        T = preset*1000
        self.clock = 0 if up else preset
        for _ in self.pause(T):
            self.clock = self.clock+1 if up else self.clock-1
            yield from self.pause(1000)
        self.clock = preset if up else 0
    
    def emergency(self,value: bool = True ):
        self.log(f'аварийный режим = {value}')
        self.f_loaded.unset( )
        self.ready = False
        self.sfc_reset = value
        self.f_loaded.unset()
    
    def __always(self):
        if self.f_ack.q: self.req=False
        if self.f_nack.q: self.req=True

    def __counting(self):
        i = 0
        for e in self.expenses:
            e( )
            setattr( self,f'expense_{i}',e.e )
            i+=1

    def start(self,count:int=None,mixT:int=None,unloadT:int=None):
        self.count = self.count if count is None else count
        self.mixT = self.mixT if mixT is None else mixT
        self.unloadT = self.unloadT if unloadT is None else unloadT
        self.f_go(clk=True)
        self.ready = False

    def __cycle(self,batch = 0):
        if self.gate and not self.gate.closed:
            self.state = 'ЗАКРЫТЬ'
            self.log('ждем закрытия затвора...')
            for _ in self.until(lambda: self.gate.closed, step = 'closing'):
                self.gate.lock = True
                self.clock = 0
                yield
            self.gate.lock = False
        
        if self.motor and not self.motor.ison:
            self.log('ждем включения двигателя...')
            self.state = 'ВКЛЮЧИТЬ'
            yield from self.until(lambda: self.motor.ison,step = 'turn.on' )

        self.state=f'НАБОР<sup>{batch+1}/{self.count}</sup>'
        self.load = True
        yield 
        self.load = False
        
        self.log(f'ждем набора #{batch+1} замеса')
        timer = self.exec(self.timer(999))
        for _ in self.until( lambda: self.f_loaded.q  ):
            if self.loading: self.state=f'ЗАГРУЗКА<sup>{batch+1}/{self.count}</sup>'
            yield from self.pause(1000)
        timer.close( )
        self.loading = False
        self.loaded = False
        self.f_loaded.unset( )

        if batch==0:
            self.req = True

        self.log(f'перемешивание #{batch+1}/{self.count}')
        self.ready = batch+1==self.count
        count = self.count
            
        self.state=f'ПЕРЕМЕШИВАНИЕ<sup>{batch+1}/{count}</sup>'
        yield from self.exec( self.timer(self.mixT,up=False) )

        self.log(f'выгрузка #{batch+1}/{self.count}')
        if self.gate:
            if self.use_ack:
                self.state = f'ПОДТВЕРДИ<sup>{batch+1}/{count}</sup>'
                for x in self.till(lambda: self.req,step='ack'):
                    yield x
            self.state=f'ВЫГРУЗКА<sup>{batch+1}/{count}</sup>'
            self.gate.simple( pt=self.unloadT )
                
            self.exec(self.timer(self.unloadT,up = False))
            yield from self.till( lambda: self.gate.unloading,min = self.unloadT*1000 )
        else:
            yield from self.exec(self.timer(self.unloadT, up = False) )
        self.clock = 0

    def main(self) :
        self.log('готов')
        self.state = 'СВОБОДНА'
            
        for _ in self.until( lambda: self.go , step ='ready'):
            self.ready = True
            yield 
        for _ in self.till( lambda: self.go , step = 'steady'):
            self.ready = False
            yield 

        self.ready = False
        self.log(f'начало замеса(ов): {self.count} шт')
        batch = 0
        self.state = 'ПОДГОТОВКА'
        count = self.count
        while batch<count and not self.sfc_reset:
            yield from self.__cycle(batch)

            batch += 1
            if not self.ready:
                count = self.count


from pyplc.sfc import *
from pyplc.utils.trig import RTRIG,FTRIG
from pyplc.utils.latch import RS
from .factory import Factory
from .counting import Flow,Expense

@sfc( inputs=['go','count'],vars=['ready','clock','state','mixT','unloadT','qreset','ack','req','nack','forbid'] )
class Mixer(SFC):
    """Смеситель

    Args:
        go ( bool ) : запуск цикла работы
        gate ( MSGate ): управление затвором выгрузки
        loaded ( bool ): сигнал "смеситель загружен"
        load ( bool ): сигнал "можно загружать"
    """
    def __init__(self, count=1,gate=None, motor=None, go=False, loaded=False, load = False, factory:Factory = None, flows : list[Flow]=None ):
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
        self.clock = 0
        self.state = 'СВОБОДНА'
        self.f_go = RTRIG( clk = lambda: self.go , id = 'f_go')
        self.f_ack = FTRIG( clk = lambda: self.ack, id= 'f_ack')
        self.f_nack = FTRIG( clk = lambda: self.nack)
        self.f_loaded = RS( set = lambda: self.loaded, id = 'f_loaded' )
        self.factory = factory
        self.qreset = False
        if flows is not None:
            self.expenses=[ Expense( flow_in = f ,out = lambda: self.qreset ) for f in flows ]
            for i in range(0,len(flows)):
                setattr(self,f'expense_{i}',0.0)
                self.export(f'expense_{i}')
        else:
            self.expenses=[ ]

        self.subtasks = [self.f_loaded,self.__counting,self.__always,self.f_go,self.f_ack,self.f_nack]
    
    @sfcaction
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
        while self.T<T and not self.sfc_reset:
            self.clock = int( self.T/1000) if up else int((T-self.T)/1000)
            for i in self.pause(1000):
                yield i
        self.clock = preset if up else 0
    
    def emergency(self,value: bool = True ):
        self.log(f'emergency = {value}')
        self.f_loaded.unset( )
        self.ready = False
        self.sfc_reset = value
    
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
            self.log('waiting for gate become closed...')
            for x in self.until(lambda: self.gate.closed, step = 'closing'):
                self.gate.lock = True
                self.clock = self.T
                yield True
            self.gate.lock = False
        
        if self.motor and not self.motor.ison:
            self.log('waiting for motor turn on')
            self.state = 'ВКЛЮЧИТЬ'
            for x in self.until(lambda: self.motor.ison,step = 'turn.on' ):
                yield x

        self.log(f'ready for knead #{batch}')
        self.state=f'НАБОР<sup>{batch+1}/{self.count}</sup>'
        self.load = True
        yield True
        self.load = False
        
        self.log(f'wait for loaded')
        timer = self.exec(self.timer(999))
        for x in self.until( lambda: self.f_loaded.q  ):
            if self.loading: self.state=f'ЗАГРУЗКА<sup>{batch+1}/{self.count}</sup>'
            yield x
        timer.close( )
        self.loaded = False
        self.f_loaded.unset( )

        if batch==0:
            self.req = True

        self.log('mixing...')
        self.ready = batch+1==self.count
        count = self.count
            
        self.state=f'ПЕРЕМЕШИВАНИЕ<sup>{batch+1}/{count}</sup>'
        for x in self.exec( self.timer(self.mixT,up=False) ).wait:
            yield x

        self.log('unloading')
        if self.gate:
            self.state = f'ПОДТВЕРДИ<sup>{batch+1}/{count}</sup>'
            for x in self.till(lambda: self.req,step='ack'):
                yield x
            self.state=f'ВЫГРУЗКА<sup>{batch+1}/{count}</sup>'
            if not self.sfc_reset:
                self.gate.simple( pt=self.unloadT )
                
            self.exec(self.timer(self.unloadT))
            for x in self.till( lambda: self.gate.unloading,min = self.unloadT*1000 ):
                yield x
        else:
            for x in self.exec(self.timer(self.unloadT) ).wait:
                yield x
        self.clock = 0

    @sfcaction
    def main(self) :
        self.log('ready')
        self.state = 'СВОБОДНА'
            
        for x in self.until( lambda: self.go , step ='ready'):
            self.ready = True
            yield x
        for x in self.till( lambda: self.go , step = 'steady'):
            self.ready = False
            yield x

        self.ready = False
        self.log(f'starting {self.count} kneads...')
        batch = 0
        self.state = 'ПОДГОТОВКА'
        count = self.count
        while batch<count and not self.sfc_reset:
            for x in self.__cycle(batch):
                yield x
            batch += 1
            if not self.ready:
                count = self.count
            self.log(f'complete {batch}/{count}')

        self.log(f'finished {batch} kneads')


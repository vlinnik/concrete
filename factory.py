from pyplc.pou import POU
from pyplc.utils.trig import TRIG
from pyplc.utils.misc import TON
import time

class Factory(POU):
    CODES = []
    LIMIT = 115
    HOUR = 18000000

    manual = POU.var(True)
    emergency = POU.var(False)
    powerfail = POU.var(True)
    powerack = POU.var(False)
    over = POU.var(False)
    scanTime = POU.var(0)

    activated = POU.var(False,persistent=True)
    moto = POU.var(0,persistent=True)
    used = POU.var(0,persistent=True)
    powered = POU.var(0,persistent=True)

    def __init__(self,id:str = None,parent:POU=None) -> None:
        super().__init__( id,parent )
        self.manual = True
        self.emergency = False
        self.powerfail = True
        self.powerack = False
        self.imitation = False
        self.f_manual = TRIG(clk = lambda: self.manual)
        self.f_emergency = TRIG(clk = lambda: self.emergency )
        self.f_powerack = TON(clk = lambda: self.powerack,pt=2000)
        self.hour = TON(pt=Factory.HOUR)
        self.moto = 0
        self.used = 0
        self.code = 0
        self.activated = False
        self.over = False
        self.powered = 0
        self.last_call = time.time_ns( )
        self.on_mode = [lambda *args: self.log('ручной режим = ',*args)]
        self.on_emergency = [lambda *args: self.log('аварийный режим = ',*args)]
    def trial(self):
        if self.activated:
            return
        if self.over:
            self.manual = True
            if self.code in Factory.CODES:
                index = Factory.CODES.index(self.code)
                if self.used & (1<<index):
                    return
                self.used = self.used | (1<<index)
                self.over = False
                self.activated = index==15
            return
        if not self.hour(clk=not self.hour.q):
            return
        self.moto+=1
        self.over = self.moto>Factory.LIMIT
            

    def __call__(self) :
        with self:
            self.scanTime = int((POU.NOW_MS - self.last_call))
            self.last_call = POU.NOW_MS
            # self.trial( )
            if self.f_manual( ):
                for e in self.on_mode:
                    e( self.manual )
            if self.f_emergency( ):
                for e in self.on_emergency:
                    e( self.emergency )
                
            if self.f_powerack( ) and self.powerfail:
                self.log(f'перезагрузка/отключение зарегистрировано')
                self.powerfail = False
                self.powerack = False
                self.powered += 1
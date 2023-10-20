from pyplc.stl import *
from pyplc.utils.trig import TRIG
from pyplc.utils.misc import TON
import time

@stl(vars=['manual','emergency','powerfail','powerack','imitation','moto','used','code','activated','over','scanTime','powered'],persistent=['moto','used','activated','over','powered'])
class Factory(STL):
    CODES = [492514677,966469493,479980427,240744683,701396280,550554374,993031528,853155165,307705131,476236431,740255561,206650223,664642972,191186618,887119234,859155162]
    LIMIT = 115
    HOUR = 18000000
    def __init__(self) -> None:
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
        self.on_mode = [lambda *args: print(f'#{self.id}: manual toggled ',*args)]
        self.on_emergency = [lambda *args: print(f'#{self.id}: emergency toggled ',*args)]
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
            now = time.time_ns( )
            self.scanTime = int((now - self.last_call)/1000000)
            self.last_call = now
            # self.trial( )
            if self.f_manual( ):
                for e in self.on_mode:
                    e( self.manual )
            if self.f_emergency( ):
                for e in self.on_emergency:
                    e( self.emergency )
                
            if self.f_powerack( ) and self.powerfail:
                print(f'#{self.id}: power fail acknowledged')
                self.powerfail = False
                self.powerack = False
                self.powered += 1
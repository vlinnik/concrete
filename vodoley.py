from pyplc.sfc import *
from pyplc.utils.trig import FTRIG
from pyplc.utils.misc import BLINK
from .factory import Factory
from .counting import RotaryFlowMeter

# @sfc(inputs=['sp','humidity','clk','go'],outputs=['out'],vars=['w0','t0','w1','t1','preT','postT','state','clock','precise','speed','enable','vol'])
class Vodoley(SFC):
    @POU.init
    def __init__(self,sp=0.0,humidity=0.0,clk = False, go = False,factory: Factory = None ) -> None:
        super( ).__init__( )
        self.sp = sp
        self.humidity = humidity
        self.clk = clk
        self.go = go
        self.out = False
        self.w0 = 3000.0
        self.t0 = 2.0
        self.w1 = 500.0
        self.t1 = 5.0
        self.preT = 15
        self.postT = 20
        self.state = 'ГОТОВ'
        self.clock = 0
        self.precise = 0.5/100.0 * 65535
        self.speed = 0.0
        self.enable = False
        self.vol = 1.0
        self.factory = factory
        self.complete = False
        self.f_go = FTRIG(clk = lambda: self.go )   #
        self.water = RotaryFlowMeter(clk = lambda: self.clk, flow_in = lambda: self.out ) #подсчет расхода
        self.blink = BLINK( )
        self.subtasks = [ self.__reset ]
        pass

    def __reset(self):
        if self.factory and self.factory.emergency:
            self.sfc_reset = True
            return True
        self.sfc_reset = False
        return False

    def __auto(self,out:bool = None):
        if self.factory and self.factory.manual:
            return
        if out is not None:
            self.out = out

    @sfcaction
    def main(self) :
        if self.sfc_reset:
            return

        self.clock = 0
        self.state = 'ГОТОВ'
        self.blink.enable = False
        self.log('ready')
        for x in self.until( self.f_go):
            self.blink(enable = False)
            yield x

        if self.humidity<self.sp:
            self.state = 'ПЕРЕМЕШИВАНИЕ'
            self.log('premixing')
            for x in self.pause(self.preT):
                self.clock = self.T
                yield x

        if self.speed>0:
            self.state = 'ПРЕДНАЛИВ 0%'
            water_q = (self.sp - self.humidity)/65535*100.0*self.vol*self.speed
            self.log(f'adding water with rotary flowmeter, approx {water_q}')
            self.water.clear()
            for x in self.till(lambda: self.water.e<water_q):
                self.water( )
                self.__auto(out=True)
                if f'ПРЕДНАЛИВ {int(100.0*self.water.e/water_q)}%'!=self.state:
                    self.state = f'ПРЕДНАЛИВ {int(100.0*self.water.e/water_q)}%'
                yield x
            self.__auto(out=False)
            self.log('water with rotary flowmeter added')
            self.state = 'ПЕРЕМЕШИВАНИЕ'
            self.log('post mixing')
            for x in self.pause(self.postT):
                self.clock = self.T
                yield x

        if self.humidity<self.sp:
            self.log('rought hydration')
            self.state = 'ГРУБО'
            for x in self.till(lambda: self.humidity<self.sp-self.precise):
                self.clock = self.T
                self.__auto( out = self.blink(enable=True,t_on = 0.001*self.w0,t_off = self.t0) )
                yield x
            self.log('finalizing rought hydration')
            self.state = 'ПЕРЕХОД'
            self.__auto(out=False)
            yield self.pause(self.t1)

            self.log('precise hydration')
            self.state = 'ТОЧНО'
            for x in self.till(lambda: self.humidity<self.sp):
                self.clock = self.T
                self.__auto( out = self.blink(enable=True,t_on = 0.001*self.w1,t_off = self.t1) )
                yield x
            self.log('post mixing')
            self.__auto( out = False )
            self.state = 'ПЕРЕМЕШИВАНИЕ'
            for x in self.pause(self.postT):
                self.clock = self.T
                yield x

        self.complete = True
        yield True
        self.complete = False

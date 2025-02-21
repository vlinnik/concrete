from pyplc.sfc import *
from .container import FlowMeter

class Vodoley(FlowMeter):
    humidity = POU.input(0,hidden=True)
    w0 = POU.var(3,persistent=True )      #сколько литров налить
    t0 = POU.var(2.0,persistent=True )    #сколько секунд пауза
    w1 = POU.var(1,persistent=True )
    t1 = POU.var(5.0, persistent=True )
    preT = POU.var(15, persistent=True)
    postT= POU.var(20,persistent=True)
    state= POU.var('ГОТОВ')
    speed= POU.var(100,persistent=True)   #управление споростью подачи
    precise=POU.var(328,persistent=True)  #переход на точный
    hum_sp   = POU.var(0,persistent=True) #целевая влажность
    wpp    = POU.var(1,persistent=True)   #сколько л воды на 1% влажности надо набрать
    clock  = POU.var(0)
    mode = POU.var(0)
    
    MODE_Q    = 0
    MODE_CALC = 1
    MODE_AUTO = 2
    
    def __init__(self,humidity: int=0, clk:bool = False, out:bool = False,id:str = None,parent:POU = None ) -> None:
        super( ).__init__( clk=clk, out=out, id=id, parent=parent)
        self.humidity = humidity
        self.out = out
        self.clk = clk
        
    def pulse(self, t:callable):
        yield from super().progress( )
        self.remote(False)
        self.clock = 0 
        while self.clock<t( ):
            self.clock+=1 
            yield from self.pause( 1000 )
            
    def timer(self,t: callable):
        self.clock = 0
        while self.clock < t():
            self.clock+=1
            yield from self.pause(1000)
                
    def progress(self):
        if self.mode==Vodoley.MODE_Q:
            self.state = 'РАСХОД'
            yield from super().progress()
        elif self.humidity<self.hum_sp:
            if self.mode==Vodoley.MODE_CALC:
                self.state = 'ПРЕД ПЕРЕМЕШИВАНИЕ'
                self.log('предварительное перемешивание')
                yield from self.timer(lambda: self.preT)
                self.state = 'ПО РАСЧЕТУ'
                self.sp = (self.hum_sp - self.humidity)/65535*self.wpp*self.speed
                self.log(f'по расчету нужно налить {self.sp}')
                yield from super().progress()
                self.state = 'ПОСТ ПЕРЕМЕШИВАНИЕ'
                yield from self.timer(lambda: self.postT)
            else:
                self.state = 'ГРУБО'
                beginAt = self.humidity
                beginQ = self.done
                self.sp = self.w0
                while self.humidity<self.hum_sp-self.precise:
                    yield from self.pulse(lambda: self.t0)
                
                self.state = 'ТОЧНО'
                self.sp = self.w1
                while self.humidity<self.hum_sp:
                    yield from self.pulse(lambda: self.t1)
                    
                self.state = 'ПОСТ ПЕРЕМЕШИВАНИЕ'
                yield from self.timer(lambda: self.postT)
                
                endAt = self.humidity
                endQ = self.done
                if endAt>beginAt and endQ>beginQ:
                    self.sp = endQ - beginQ
                    wpp = (endQ-beginQ)/((endAt - beginAt)/65535*100)
                    self.log(f'расчетная характеристика {wpp:.3f}')
                    self.wpp = wpp
                
                
    
    def main(self):
        self.state = 'ГОТОВ'
        yield from super().main( )
        
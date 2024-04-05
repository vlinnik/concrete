from pyplc.stl import *
from pyplc.pou import POU
from pyplc.utils.trig import FTRIG
    
class Weight(STL):
    g_Load = 0.0
    raw = POU.input( 0 , hidden=True)
    m = POU.output(0.0)
    k = POU.var(1.0,persistent=True,hidden=True)
    a = POU.var(0.0,persistent=True,hidden=True)
    mA= POU.var(4.0)
    shift=POU.var(False)
    set = POU.var(False)
    step =POU.var(0.1,persistent=True)
    def __init__(self,raw: int =0, mmax:int =None,id: str=None,parent: POU=None):
        super().__init__( id, parent )
        self.raw = raw
        self.__raw = self.raw #для определения still
        self.k=100/16 if mmax is None else mmax/16
        self.a=0.0
        self.mA = 4.0
        self.hist=[0]*4
        self.points=[]
        self.shift = False
        self.set = False
        self.still = True
        self.ok = False
        self.m = 0.0
        self.slow_m = 0.0   #для учета среднее по последним 4 измерениям (hist)
        self.fast_m = 0.0   #для дозирования без округления по step
        self.step = 0
        self.f_shift = FTRIG(clk=lambda: self.shift)
        self.f_set = FTRIG(clk=lambda: self.set)
        self.h_index = 0
    
    def tune(self,load):
        self.points.append( (self.mA,load) )
        if len(self.points)>1:
            self.points.sort(key=lambda pt: pt[0])
            mA0,m0 = self.points[0]
            mA1,m1 = self.points[-1]
            if abs(mA1 - mA0)>=0.005:
                self.k = (m1-m0)/(mA1-mA0)
                self.a = m1 - (mA1-4)*self.k
                self.points.clear()

    def __call__(self,raw:int=None):
        with self:
            raw = self.overwrite('raw',raw)
            if raw is not None:
                self.hist[self.h_index]=raw & 0xFFFC
                self.h_index = (self.h_index+1) % 4
                if self.h_index==0:
                    self.mA  = sum(self.hist)/0x10000*4 # optimized sum(self.hist)/4/65535*16 + 4
                    self.slow_m = self.mA * self.k + self.a
                    self.mA += 4
                    if self.__raw is not None:
                        self.still = abs(raw - self.__raw)<650 #изменение менее чем 2% 
                    else:
                        self.still = True
                    self.__raw = raw
    
                if self.f_shift():
                    self.a = -(self.mA-4)*self.k
                if self.f_set():
                    self.tune( Weight.g_Load )

                self.fast_m = ( (raw & 0xFFFC)/0x1000 )*self.k + self.a

                if self.step>0:
                    self.m = self.step*int(self.fast_m/self.step)
                else:
                    self.m = self.fast_m
                self.ok = True
            else:
                self.ok = False

        return self.m
from pyplc.stl import *
from pyplc.utils.trig import FTRIG
    
@stl(inputs=['raw'],outputs=['m','ok'],vars=['k','a','mA','shift','set','step'],persistent=['k','a'],hidden=['raw','ok','k','a'])
class Weight(STL):
    g_Load = 0.0
    def __init__(self,raw=0,mmax=None):
        self.__raw = raw #для определения still
        self.raw = raw
        self.fast = False
        self.k=100/16 if mmax is None else mmax/16
        self.a=0.0
        self.mA = 4.0
        self.hist=[0]*4
        self.points=[]
        self.ok = False
        self.shift = False
        self.set = False
        self.still = True
        self.m = 0.0
        self.step = 0
        self.f_shift = FTRIG(clk=lambda: self.shift)
        self.f_set = FTRIG(clk=lambda: self.set)
        self.h_index = 0
    
    def mode(self,fast: bool):
        self.fast = fast
        
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

    def __call__(self,raw=None,fast=None):
        with self:
            raw = self.overwrite('raw',raw)
            fast = self.overwrite('fast',fast)
            if raw is None: return 0
            self.hist[self.h_index]=raw
            self.h_index = (self.h_index+1) % 4
            if self.h_index==0:
                self.mA  = sum(self.hist)/0x10000*4 # optimized sum(self.hist)/8/65535*16 
                if not fast: 
                    self.m = self.a + self.mA*self.k 
                self.mA += 4
                if raw is not None and self.__raw is not None:
                    self.still = abs(raw - self.__raw)<650 #изменение менее чем 2% 
                self.__raw = raw
            self.ok = True

            if self.f_shift():
                self.a = -(self.mA-4)*self.k
            if self.f_set():
                self.tune( Weight.g_Load )

            if fast:
                self.m = (raw/0x1000)*self.k + self.a    #optimized raw/0x10000*16*self.k + self.a

            if self.step>0:
                self.m = self.step*int(self.m/self.step)
        return self.m
from pyplc.stl import *
from pyplc.utils.misc import TOF
from pyplc.utils.trig import FTRIG,TRIG,RTRIG

class Flow():
    def __init__(self):
        self.m = 0
        self.clk = False

    def __str__(self):
        return f'Flow=<clk={self.clk},m={self.m}>'
    def __call__(self, clk: bool, m: float ):
        self.m = m
        self.clk = clk

@stl(inputs=['flow_in','flow_out'],outputs=['e'])
class Counter(STL):
    def __init__(self,m=0.0, flow_in = False, flow_out = False) -> None:
        self.flow_in = flow_in
        self.flow_out = flow_out 
        self.__m = m
        self.m = m
        self.e = 0.0
        self.q = Flow( )
        # self.filter = TOF(clk = lambda: self.flow_in,pt=1000 )
        self.f_out = FTRIG(clk = lambda: self.flow_out )
        self.trig = TRIG(clk = lambda: self.flow_in)

    def __call__(self, m = None) :
        with self:
            self.m = self.overwrite('m',m)
            
            # self.filter( )
            self.f_out( )
            self.q(self.flow_out,self.e )
            if self.f_out.q:
                self.e = 0 

            if self.trig( ):
                if self.flow_in:
                    self.__m = self.m
                else:
                    self.e += self.m - self.__m
                    self.__m = self.m

@stl(inputs=['out'],outputs=['e'])
class Expense(STL):
    def __init__(self,flow_in: Flow,out=None):
        self.out = out
        self.e = 0.0
        self.q = Flow( )
        self.flow_in = flow_in
        self.f_in = RTRIG( clk =lambda: self.flow_in.clk )
        self.f_out = FTRIG( clk = lambda: self.out )

    def __call__(self, out = None):
        with self:
            self.out = self.overwrite('out',out)
            self.f_in( )
            if self.f_in.q:
                self.e += self.flow_in.m

            self.f_out( )
            if self.f_out.q:
                self.e = 0.0
            self.q(not self.out,self.e)

@stl(inputs=['clk','rst','flow_in'],outputs=['e'])
class RotaryFlowMeter(STL):
    def __init__(self,weight:float = 1.0,clk:bool=False,rst:bool=False,flow_in:bool=True):
        self.e = 0.0
        self.weight = weight
        self.clk = clk
        self.rst = rst
        self.flow_in = flow_in
        self.q = Flow( )
        self.f_in = FTRIG( clk =lambda: self.clk )
        self.f_out = FTRIG( clk=lambda: self.rst )
    def clear(self):
        self.e = 0

    def __call__(self) :
        if self.f_in() and self.flow_in:
            self.e+=self.weight
        self.q(self.flow_in,self.e)
        if self.f_out():
            self.e = 0

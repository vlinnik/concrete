from pyplc.pou import POU
from pyplc.utils.misc import TOF
from pyplc.utils.trig import FTRIG,TRIG,RTRIG

class Flow():
    """Вспомогательный класс для работы с перемещением материалов (расход)
    """
    def __init__(self):
        self.m = 0
        self.clk = False

    def __str__(self):
        return f'Flow=<clk={self.clk},m={self.m}>'
    def __call__(self, clk: bool, m: float ):
        self.m = m
        self.clk = clk

class Counter(POU):
    flow_in = POU.input(False)
    flow_out= POU.input(False)
    m = POU.input(0.0)
    e = POU.output(0.0)
    @POU.init
    def __init__(self,m=0.0, flow_in = False, flow_out = False) -> None:
        super().__init__( )
        self.flow_in = flow_in
        self.flow_out = flow_out 
        self.__m = None
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
                if self.flow_in or self.__m is None:
                    self.__m = self.m
                else:
                    self.e += self.m - self.__m
                    self.__m = self.m

class MoveFlow(POU):
    """
    Перенос накопленного расхода по out. 
    Применение: например скип после конвейера расходы с конвейера переносит в момент верхнего положения
    """ 
    out = POU.input(False)   
    e = POU.output(0.0)
    def __init__(self,flow_in: Flow,out: bool = False, id: str=None, parent:POU=None):
        super().__init__( id,parent)
        self.out = out
        self.e = 0.0
        self.q = Flow( )
        self.flow_in = flow_in
        self.f_in = RTRIG( clk =lambda: self.flow_in.clk )
        self.f_out = FTRIG( clk = lambda: self.out )

    def __call__(self, out = None):
        with self:
            self.out = self.overwrite('out',out)
            if self.f_in( ):    #загрузили
                self.e += self.flow_in.m

            self.q(not self.out,self.e)

            if self.f_out( ):   #выгрузили
                self.e = 0.0

class Expense(POU):
    out = POU.input(False)
    e = POU.output(0.0)
    @POU.init
    def __init__(self,flow_in: Flow,out:bool=False):
        super().__init__( )
        self.out = out
        self.e = 0.0
        self.q = Flow( )
        self.flow_in = flow_in
        self.f_in = RTRIG( clk =lambda: self.flow_in.clk )
        self.f_out = FTRIG( clk = lambda: self.out )

    def __call__(self, out:bool = None):
        with self:
            self.out = self.overwrite('out',out)
            self.f_in( )
            if self.f_in.q:
                self.e += self.flow_in.m

            self.f_out( )
            if self.f_out.q:
                self.e = 0.0
            self.q(not self.out,self.e)

class RotaryFlowMeter(POU):
    clk = POU.input(False)
    rst = POU.input(False)
    flow_in = POU.input(True)
    e = POU.output(0.0)

    def __init__(self,weight:float = 1.0,clk:bool=False,rst:bool=False,flow_in:bool=True,id:str = None,parent: POU = None):
        super().__init__( id,parent )
        self.__e = 0.0
        self.e = 0.0
        self.weight = weight
        self.clk = clk
        self.rst = rst
        self.flow_in = flow_in
        self.q = Flow( )
        self.f_in = FTRIG( clk =lambda: self.clk )
        self.f_out = FTRIG( clk=lambda: self.rst )
        
    def clear(self):
        self.e = 0.0

    def __call__(self):
        with self:
            if self.f_in() and self.flow_in:
                self.e+=self.weight
            self.q(self.flow_in,self.e)
            if self.f_out():
                self.e = 0

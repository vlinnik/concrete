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

class Counter():
    def __init__(self,m: callable , flow_in: callable , flow_out: callable) -> None:
        self.flow_in = flow_in
        self.flow_out = flow_out 
        self.__in = None
        self.__out= None
        self.__m = None
        self.m = m
        self.e = 0.0 # результат учета расхода
        self.q = Flow( )

    def __call__(self, m: float = None) :
        m = m if m is not None else self.m()
        
        _out = self.flow_out( )
        self.q(_out,self.e )
        if _out==False and self.__out==True:
            self.e = 0 

        _in = self.flow_in( )
        if _in!=self.__in and self.__in is not None:
            if _in or self.__m is None:
                self.__m = m
            else:
                self.e += m - self.__m
                self.__m = m
                
        self.__in = _in
        self.__out= _out

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

class Expense():
    def __init__(self,flow_in: Flow,out:callable):
        self.out = out
        self.e = 0.0        #результат вычисления расхода
        self.q = Flow( )
        self.flow_in = flow_in
        self._in = None
        self._out= None 

    def __call__(self, out:bool = None):
        out = out if out is not None else self.out()
        if self._in==False and self.flow_in.clk==True:
            self.e += self.flow_in.m
        self._in = self.flow_in.clk

        if self._out==True and out==False:
            self.e = 0.0
        self._out = out
        self.q(not out,self.e)

class RotaryFlowMeter(POU):
    cnt = POU.input(int(0)) #счетчик импульсов
    clk = POU.input(False)  #дискретный вход от импульса
    rst = POU.input(False)
    flow_in = POU.input(True)
    e = POU.output(0.0)

    def __init__(self,weight:float = 1.0,clk:bool=False,cnt:int = None, rst:bool=False,flow_in:bool=True,id:str = None,parent: POU = None):
        super().__init__( id,parent )
        self.__e = 0.0
        self.e = 0.0
        self.weight = weight
        self.cnt = cnt
        self._cnt = self.cnt    #параметр cnt может быть callable|None|int, а self.cnt - int или None
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
            if self.flow_in and self.cnt!=self._cnt:
                #счетчик self.cnt = [0;255], учитываем переполнение
                self.e+= ((self.cnt - self._cnt) if self.cnt>=self._cnt else (self.cnt + 256-self._cnt))*self.weight
                self._cnt = self.cnt
            if self.f_in() and self.flow_in:
                self.e+=self.weight
            self.q(self.flow_in,self.e)
            if self.f_out():
                self.e = 0

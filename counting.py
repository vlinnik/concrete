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
    """Учет расхода по 2 потокам: вход и выход. flow_in прикрепляется к TOF от входного затвора, flow_out к сигналу отсутствия герметичности 
    дозатора. В обычной схеме при создании Container создается с flow_out = None, в Dosator происходит install_counter где flow_out подключается
    к герметичности Dosator
    """
    def __init__(self,m: callable , flow_in: callable , flow_out: callable = None) -> None:
        self.flow_in = flow_in
        self.flow_out = flow_out 
        self.__in = None
        self.__out= None
        self._m = None
        self.m = m
        self.live= 0.0
        self.e = 0.0 # результат учета расхода
        self.q = Flow( )

    def __str__(self):
        return f'Counter=<in={self.__in},out={self.__out},m={self.m}>'

    def reset_when(self,rst:callable):
        self.flow_out = rst
        self.__out = rst( )

    def __call__(self, m: float = None) :
        m = m if m is not None else self.m()
        
        _out = self.flow_out( )
        _in = self.flow_in( )
        if _in!=self.__in and self.__in is not None:
            if _in or self._m is None:
                pass #self.__m = m
            else:
                self.e += m - self._m
                self._m = m
        elif not _in:
            self._m = m
        self.q(_out,self.e )
        if _in and self._m is not None:
            self.live = self.e + (m - self._m)
        if _out==False and self.__out==True:
            self.e = 0 
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
            if out is not None: self.out = out
            if self.f_in( ):    #загрузили
                self.e += self.flow_in.m

            self.q(not self.out,self.e)

            if self.f_out( ):   #выгрузили
                self.e = 0.0
        return self.e

class Expense():
    def __init__(self,flow_in: Flow,out:callable):
        self.out = out
        self.e = 0.0        #результат вычисления расхода
        self.q = Flow( )
        self.flow_in = flow_in
        self._in = None
        self._out= None 

    def __str__(self):
        return f'Expense=<in={self._in},out={self._out},e={self.e}>'

    def __call__(self, out:bool = None):
        out = out if out is not None else self.out()
        if self._in==False and self.flow_in.clk==True:
            self.e += self.flow_in.m
        self._in = self.flow_in.clk

        if self._out==True and out==False:
            self.e = 0.0
        self._out = out
        self.q(not out,self.e)
        return self.e

class Delta():
    """Подобен Counter, только работает с Flow (Counter работает с m)
    """
    def __init__(self,flow_in: Flow,out:callable = None):
        self.out = out
        self.e = 0.0        #результат вычисления расхода
        self.q = Flow( )
        self.flow_in = flow_in
        self._in = None
        self._out= None
        self._m  = None

    def __str__(self):
        return f'Delta=<in={self._in},out={self._out},e={self.e}>'
        
    def reset_when(self,rst:callable):
        self.out = rst
        self._out = rst( )

    def __call__(self, out:bool = None):
        out = out if out is not None else (False if self.out is None else self.out())
        if self._in==False and self.flow_in.clk==True or self._m is None:
            self._m = self.flow_in.m
        if self._in==True and self.flow_in.clk==False:
            self.e = self.flow_in.m - self._m
        self._in = self.flow_in.clk

        if self._out==True and out==False:
            self.q.m = 0.0
        self._out = out
        self.q(not self._in,self.e)

class RotaryFlowMeter():
    def __init__(self,weight:float = 1.0,clk:bool=False,cnt:int = 0, rst:bool=False,flow_in:bool=True):
        self.e = 0.0            #расход
        self.weight = weight    #вес импульса
        self._cnt = cnt         #импульсы
        self.__cnt = None       #пред значение cnt
        self._clk = clk
        self.__clk= None        #пред значение clk
        self._rst = rst
        self.__rst= None        #пред значение _rst
        self._flow_in = flow_in  #идет подача (считать)
        self.q = Flow( )        #учет
        
    @property
    def clk(self):
        if callable(self._clk): 
            return self._clk()
        return self._cnt
    @property
    def cnt(self):
        if callable(self._cnt): 
            return self._cnt()
        return self._cnt
    @property
    def rst(self):
        if callable(self._rst): 
            return self._rst()
        return self._rst
    @property
    def flow_in(self):
        if callable(self._flow_in):
            return self._flow_in()
        return self._flow_in
    def reset_when(self,rst: callable):
        self._rst = rst
        self.__rst = self.rst
    def clear(self):
        self.e = 0.0

    def __call__(self):
        if self.flow_in and self.cnt!=self.__cnt:
            #счетчик self.cnt = [0;255], учитываем переполнение
            if self.__cnt is not None:
                self.e+= ((self.cnt - self.__cnt) if self.cnt>=self.__cnt else (self.cnt + 256-self.__cnt))*self.weight
            self.__cnt = self.cnt
        if self.__clk!=self.clk and self.__clk is not None and self.flow_in:
            self.e+=self.weight
        self.__clk = self.clk
        self.q(self.flow_in,self.e)
        if self.__rst!=self.rst and self.__rst:
            self.e = 0.0
        if not self.rst and self.__rst:
            self.q.m = 0.0
        self.__rst = self.rst

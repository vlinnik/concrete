from pyplc.stl import *
from pyplc.utils.misc import BLINK
from pyplc.utils.trig import TRIG
from concrete.weight import Weight
from concrete.container import Container
from concrete.dosator import Dosator

from pyplc.sfc import *

class Vibrator(SFC):
    """Вибро-обрушитель
    """
    auto = POU.var(False,persistent=True)
    q = POU.output(False)
    def __init__(self, auto: bool = False,q: bool = False,containers: list[callable]=None, weight : Weight = None,id:str=None,parent:POU=None):
        """Вибро-обрушитель.

        Args:
            auto (bool, optional): Автоматическая работа. Defaults to False.
            q (bool, optional): Управление включением. Defaults to False.
            containers (list[callable], optional): Дискретные выходы, при включении которых должно насыпаться. Defaults to None.
            weight (Weight, optional): Вес, который контролируем. Defaults to None.
            id (str, optional): _description_. Defaults to None.
            parent (POU, optional): _description_. Defaults to None.
        """
        super( ).__init__( )
        self.containers = containers
        self.weight = weight
        self.auto = auto
        self.q = q

    def __pulse(self):
        self.log('включение вибратора')
        self.q = True
        yield from self.pause(500)
        self.q = False
        yield from self.pause(3000)

    def main(self):
        if self.weight is None or self.containers is None or not self.auto: return

        clk = False #определим включение есть/нет
        for c in self.containers:
            clk = clk or c()

        if not clk: #если нет включения ничего не делаем
            return
        
        while clk and self.auto:
            before_m = self.weight.raw
            yield from self.__pulse( )
            after_m = self.weight.raw
            if abs(before_m-after_m)>500:
                break
            
            clk = False #определим включение есть/нет
            for c in self.containers:
                clk = clk or c()
        
class UnloadHelper(SFC):
    auto = POU.input(False,persistent=True)
    q = POU.output(False)
    ignore_dm = POU.var(False,persistent=True)
    def __init__(self,auto=False,q:bool = False, dosator: Dosator=None, weight : Weight = None, point: int = None,id:str=None,parent:POU=None):
        super( ).__init__( id=id, parent=parent)
        self.dosator = dosator
        self.weight = weight
        self.auto = auto
        self.q = q
        self.point = point

    def __pulse(self):
        self.q = True
        yield from self.pause(500)
        self.q = False
        yield from self.pause(3000)

    def main(self):
        if self.weight is None or self.dosator is None or not self.auto: return

        if not self.dosator.out: #если нет включения ничего не делаем
            return
        
        while self.auto and self.dosator.out:
            if self.point is not None:
                while self.weight.m>self.point and self.dosator.out:
                    yield 
                if self.dosator.out:
                    yield from self.__pulse( )
                yield from self.till(lambda: self.dosator.out)
            else:
                before_m = self.weight.raw
                yield from self.pause(3000)
                after_m = self.weight.raw
                if abs(before_m-after_m)<500 or self.ignore_dm:
                    yield from self.__pulse( )

from pyplc.sfc import *
from pyplc.utils.trig import FTRIG

class MSGate(SFC):
    """Пневматический затвор

    Args:
        open (bool): Управление сигналом "открыть"
        unloaded (bool): Сигнал выгрузка завершена
        opened (bool): Состояние "затвор открыт"
        closed (bool): Состояние "затвор закрыт"
    """
    forbid = POU.input(False,hidden=True)
    closed = POU.input(False,hidden=True)
    opened = POU.input(False,hidden=True)
    lock = POU.input(False)
    open = POU.output(False)
    manual = POU.var(False)
    unloading = POU.var(False)
    dr = POU.var(0,persistent=True)
    E_NONE = 0
    E_JAM = -1
    def __init__(self, closed:bool = True, opened:bool=False, open:bool = False,lock:bool = False, forbid: bool=False, id:str=None,parent:POU=None) -> None:
        super().__init__(id,parent)
        self.closed = closed
        self.opened = opened
        self.open = open
        self.forbid = forbid
        self.unload = False
        self.unloaded = False
        self.unloading = False
        self.error = MSGate.E_NONE
        self.lock = lock
        self.pt = 10
        self.move_t = 10
        self.manual = False
        self.dr = 0             #в мсек время открытия 

    def emergency(self,value: bool = True ):
        self.log(f'аварийный статус = {value}')
        self.sfc_reset = value
    
    def set_lock(self, val: bool):
        if val is not None:
            self.lock = val

    def __auto( self,open ):
        if not self.manual:
            self.open = open

        self.open = self.open and not self.lock

    def __start_unload(self):
        self.unload = True
        yield
        self.unload = False

    def __begin_open(self,pt = 3000):
        self.error = MSGate.E_NONE
        while self.closed:
            self.__auto( True )
            for _ in self.till( lambda: self.closed, max=pt ):
                self.__auto( True )
                yield 
            if self.closed:
                self.log(f'заклинивание в закрытом состоянии')
                self.__auto( False )
                self.error = MSGate.E_JAM
                yield from self.pause(1000)
        self.__auto( True )
        self.error = MSGate.E_NONE

    def __begin_close(self,pt=3000):
        self.error = MSGate.E_NONE
        while self.opened:
            self.__auto( False )
            yield from self.till( lambda: self.opened, max=pt )
            if self.opened:
                self.log('заклинило в открытом положении')
                self.__auto( True )
                self.error = MSGate.E_JAM
                yield from self.pause( 1000 )
        self.__auto( False )
        self.error = MSGate.E_NONE

    def __till_opened(self,pt=None):
        pt = self.overwrite("move_t",pt)*1000
        self.error = MSGate.E_NONE
        self.log(f'до полного открытия')
        while not self.opened:
            for _ in self.until( lambda: self.opened,max=pt):
                self.__auto( True )
                yield 
            if not self.opened:
                self.log('не доходит до полного открытия')
                self.error= MSGate.E_JAM
                for _ in self.pause(1000):
                    self.__auto ( False )
                    yield 
        self.__auto(True)
        self.error = MSGate.E_NONE

    def __till_closed(self,pt=5000):
        self.error = MSGate.E_NONE
        while not self.closed:
            for _ in self.until( lambda: self.closed,max=pt):
                self.__auto(False)
                yield 
            if not self.closed:
                self.log('Не доходит до полного закрытия')
                self.error= MSGate.E_JAM
                for _ in self.pause(1000):
                    self.__auto(True)
                    yield
        self.__auto(False)
        self.error = MSGate.E_NONE

    def __unload(self,pt=None,move_t=None):
        self.unloading = True
        yield from self.till(lambda: self.forbid,step='forbidden')
        pt = self.overwrite('pt',pt)*1000
        move_t = self.overwrite('move_t',move_t)*1000
        self.log(f'начинаем выгрузку')

        if self.dr>0:
            for _ in self.pause( pt,step='pulse.unload' ):
                yield from self.__begin_open()
                yield from self.pause( self.dr )
                yield from self.__till_closed( pt = move_t)
            pt = 0
        else:
            yield from self.__begin_open()
            
        yield from self.__till_opened ( pt=move_t )
        self.log(f'выгрузка')
        for _ in self.pause( pt , step = 'unloading'):
            self.__auto(True)
            yield

        yield from self.__begin_close(  )
        yield from self.__till_closed( pt=move_t*1000 )
        self.log(f'выгрузка завершена')
        self.unloading = False

    def until_unloaded(self,pt=None,move_t=None):
        for x in self.__unload(pt=pt,move_t=move_t):
            yield x

    def main(self):
        f_unload = FTRIG( clk=lambda: self.unload)
        while True:
            self.unloading = not self.closed
            if self.lock:
                yield from self.__till_closed( )
            if f_unload( ):
                yield from self.__unload( )
            yield
                    
        
    def simple(self,pt=15,move_t=15):
        self.pt = pt
        self.move_t = move_t
        self.exec(self.__start_unload)
        

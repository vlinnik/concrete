from pyplc.sfc import *
from pyplc.utils.trig import FTRIG
from pyplc.utils.misc import Stopwatch

@sfc( inputs=['closed','opened','lock'],outputs=['open'],vars=['manual','unloading'],id='MSGate' )
class MSGate(SFC):
    """Пневматический затвор

    Args:
        open (bool): Управление сигналом "открыть"
        unloaded (bool): Сигнал выгрузка завершена
        opened (bool): Состояние "затвор открыт"
        closed (bool): Состояние "затвор закрыт"
    """
    E_NONE = 0
    E_JAM = -1
    def __init__(self, closed = True, opened=False, open = False,  **kwargs) -> None:
        self.closed = closed
        self.opened = opened
        self.open = open
        self.unload = False
        self.unloaded = False
        self.unloading = False
        self.error = MSGate.E_NONE
        self.lock = False
        self.pt = 10
        self.move_t = 10
        self.manual = False
        self.dr = 0             #в мсек время открытия 
        self.f_unload = FTRIG( clk=lambda: self.unload,id = 'r_unload')
    
    def set_lock(self, val: bool):
        self.lock = val

    def __auto( self,open ):
        if not self.manual:
            self.open = open

        self.open = self.open and not self.lock

    def __begin_open(self,pt = 3):
        self.error = MSGate.E_NONE
        while self.closed:
            self.__auto( True )
            for x in self.till( lambda: self.closed, max=pt*1000 ):
                self.__auto( True )
                yield True
            if self.closed:
                self.log(f'jammed in closed')
                self.__auto( False )
                self.error = MSGate.E_JAM
                for x in self.pause(1000):
                    yield x
        self.__auto( True )
        self.error = MSGate.E_NONE

    def __begin_close(self,pt=3):
        self.error = MSGate.E_NONE
        while self.opened:
            self.__auto( False )
            for x in self.till( lambda: self.opened, max=pt*1000 ):
                yield x
            if self.opened:
                self.log('jammed (full opened)')
                self.__auto( True )
                self.error = MSGate.E_JAM
                for x in self.pause( 1000 ):
                    yield x
        self.__auto( False )
        self.error = MSGate.E_NONE

    def __till_opened(self,pt=None):
        pt = self.move_t if pt is None else pt
        self.error = MSGate.E_NONE
        while not self.opened:
            for x in self.until( lambda: self.opened,max=pt*1000):
                self.__auto( True )
                yield True
            if not self.opened:
                self.log('jammed (wide opened)')
                self.error= MSGate.E_JAM
                for x in self.pause(1000):
                    self.__auto ( False )
                    yield True
        self.__auto(True)
        self.error = MSGate.E_NONE

    def __till_closed(self,pt=5):
        self.error = MSGate.E_NONE
        while not self.closed:
            for x in self.until( lambda: self.closed,max=pt*1000):
                self.__auto(False)
                yield True
            if not self.closed:
                self.log('jammed (a bit opened)')
                self.error= MSGate.E_JAM
                for x in self.pause(1000):
                    self.__auto(True)
                    yield x
        self.__auto(False)
        self.error = MSGate.E_NONE

    def __unload(self,pt=None,move_t=None):
        self.unloading = True
        pt = self.pt if pt is None else pt
        move_t = self.move_t if move_t is None else move_t
        self.log(f'opening')

        if self.dr>0:
            cnt = pt*1000/self.dr
            while cnt>0 and not self.sfc_reset:
                for x in self.__begin_open():
                    yield x
                for x in self.pause( self.dr ):
                    yield x
                for x in self.__till_closed( pt = move_t*1000):
                    yield x
                cnt-=1
            pt = self.T + 1000
        else:
            for x in self.__begin_open():
                yield x
            pt = self.T + pt*1000
            
        self.log(f'opening until opened')
        for x in self.__till_opened ( pt=move_t*1000 ):
            yield x
        self.log(f'unloading')
        if self.T<pt:
            sw = Stopwatch( clk=lambda: self.opened, pt = pt-self.T )
            for x in self.until( lambda: sw.q ):
                sw( )
                self.__auto(True)
                yield x

        self.log(f'closing')
        for x in self.__begin_close(  ):
            yield x
        self.log(f'untill closed')
        for x in self.__till_closed( pt=move_t*1000 ):
            yield x
        self.log(f'done')
        self.unloading = False

    def until_unloaded(self,pt=None,move_t=None):
        for x in self.__unload(pt=pt,move_t=move_t):
            yield x

    @sfcaction
    def main(self):
        if self.f_unload( ):
            for x in self.__unload( ):
                yield x
                
        if self.lock:
            for x in self.__till_closed( ):
                yield x
        
    def simple(self,pt=15,move_t=15):
        self.pt = pt
        self.move_t = move_t
        self.f_unload(clk=True)
        

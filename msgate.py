from pyplc.sfc import *
from pyplc.stl import STL
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
    dr = POU.var(int(0),persistent=True)
    count = POU.var(int(0),persistent=True)
    E_NONE = 0
    E_JAM = -1
    CMD_OPEN  = 1
    CMD_CLOSE =-1
    CMD_FREE  = 0
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

    def _auto( self,open ):
        if not self.manual:
            if isinstance(open,bool):
                self.open = open
            else:
                self.open = open>0

        self.open = self.open and not self.lock

    def __start_unload(self):
        self.unload = True
        yield
        self.unload = False

    def __begin_open(self,pt = 3000):
        self.error = MSGate.E_NONE
        while self.closed:
            self._auto( True )
            for _ in self.till( lambda: self.closed, max=pt ):
                self._auto( True )
                yield 
            if self.closed:
                self.log(f'заклинивание в закрытом состоянии')
                self._auto( False )
                self.error = MSGate.E_JAM
                yield from self.pause(1000)
        self._auto( True )
        self.error = MSGate.E_NONE

    def __begin_close(self,pt=3000):
        self.error = MSGate.E_NONE
        while self.opened:
            self._auto( False )
            yield from self.till( lambda: self.opened, max=pt )
            if self.opened:
                self.log('заклинило в открытом положении')
                self._auto( True )
                self.error = MSGate.E_JAM
                yield from self.pause( 1000 )
        self._auto( False )
        self.error = MSGate.E_NONE

    def __till_opened(self,pt=None):
        pt = pt*1000 if pt is not None else self.move_t * 1000 #self.overwrite("move_t",pt)*1000
        self.error = MSGate.E_NONE
        self.log(f'до полного открытия')
        while not self.opened:
            for _ in self.until( lambda: self.opened,max=pt):
                self._auto( True )
                yield 
            if not self.opened:
                self.log('не доходит до полного открытия')
                self.error= MSGate.E_JAM
                for _ in self.pause(1000):
                    self._auto ( False )
                    yield 
        self._auto(True)
        self.error = MSGate.E_NONE

    def __till_closed(self,pt=5000):
        self.error = MSGate.E_NONE
        while not self.closed:
            for _ in self.until( lambda: self.closed,max=pt):
                self._auto(False)
                yield 
            if not self.closed:
                self.log('Не доходит до полного закрытия')
                self.error= MSGate.E_JAM
                for _ in self.pause(1000):
                    self._auto(True)
                    yield
        self._auto(False)
        self.error = MSGate.E_NONE
    
    def _prepare_unload(self):
        """перед началом выгрузки проверяется forbid

        Yields:
            bool or None: не используется
        """
        self.unloading = True
        yield from self.till(lambda: self.forbid,step='forbidden')
        self.log(f'начинаем выгрузку')
        yield from self.__begin_open()
    
    def _finish_unload(self,pt:int, move_t:int):
        yield from self.__till_opened ( pt=move_t )
        self.log(f'выгрузка')
        for _ in self.pause( pt , step = 'unloading'):
            self._auto(True)
            yield

        yield from self.__begin_close(  )
        yield from self.__till_closed( pt=move_t*1000 )
        self.log(f'выгрузка завершена')
        self.unloading = False
        
        
    def _unload(self,pt=None,move_t=None):
        yield from self._prepare_unload( )

        pt = pt*1000 if pt is not None else self.pt*1000 #self.overwrite('pt',pt)*1000
        move_t = move_t*1000 if move_t is not None else self.move_t*1000 #self.overwrite('move_t',move_t)*1000
        
        if self.dr>0:
            count = 0
            T = POU.NOW + pt*1000000 #ms->ns
            for _ in self.pause( pt,step='pulse.unload' ):
                yield from self.__begin_open()
                yield from self.pause( self.dr )
                yield from self.__till_closed( pt = move_t)
                count+=1
                if count>=self.count: self.sfc_continue = True
            if POU.NOW < T:
                self.log('предел по количеству открываний исчерпан')
                pt = (T-POU.NOW)/1000000 
            else:
                pt = 1000
        else:
            yield from self.__begin_open()
            
        yield from self._finish_unload( pt, move_t )            

    def until_unloaded(self,pt=None,move_t=None):
        yield from self._unload(pt=pt,move_t=move_t)

    def main(self):
        f_unload = FTRIG( clk=lambda: self.unload)
        while True:
            self.unloading = not self.closed
            if self.lock:
                yield from self.__till_closed( )
            if f_unload( ):
                yield from self._unload( )
            yield
                    
        
    def simple(self,pt=15,move_t=15):
        self.pt = pt
        self.move_t = move_t
        self.exec(self.__start_unload)

class MPGate(MSGate):
    """Затвор смесителя гидравлический. Поддерживает режим выгрузки шагами: открыть-постоять-открыть еще...
    """
    close = POU.output(False)
    middle_t = POU.var(int(1000),persistent=True)   #< время остановки после шага
    
    def __init__(self, closed:bool = True, opened:bool=False, open:bool = False, close:bool = False, lock:bool = False, forbid: bool=False, id:str=None,parent:POU=None) -> None:
        super().__init__( closed=closed,opened=opened,open=open,lock=lock,forbid=forbid,id=id,parent=parent)
        self.close = close 
        
    def _auto(self, open):
        if isinstance(open,bool):
            self.open  = open and not self.opened and not self.lock
            self.close = (not open or self.lock) and not self.closed
        elif isinstance(open,int):
            self.open  = open==MPGate.CMD_OPEN and not self.opened and not self.lock
            self.close = open==(MPGate.CMD_CLOSE or self.lock) and not self.closed
    
    def _unload(self, pt:int=None, move_t:int=None):
        """алгоритм выгрузки. 

        Args:
            pt (int, optional): время выгрузки в сек. Defaults to self.pt
            move_t (int, optional): время полного открытия в сек. Defaults to self.move_t
        """
        if self.middle_t==0 or self.dr==0:
            yield from super()._unload(pt,move_t)
            return
        
        pt = pt*1000 if pt is not None else self.pt*1000 #self.overwrite('pt',pt)*1000
        move_t = move_t*1000 if move_t is not None else self.move_t*1000 #self.overwrite('move_t',move_t)*1000
        
        yield from self._prepare_unload( )

        T = POU.NOW + pt*1000000 #ms->ns
        count = 0
        for _ in self.pause( pt,step='step-by-step.unload' ):
            yield from self.pause( self.dr, step='step-by-step.move' )
            self._auto(MPGate.CMD_FREE)   #stop opening
            yield from self.pause( self.middle_t, step='step-by-step.stay' )
            self._auto(MPGate.CMD_OPEN)   #open more
            count+=1
            if self.opened or count>=self.count: self.sfc_continue = True
            
        if POU.NOW < T:
            self.log('затвор полностью открылся. остаток просто постоим')
            pt = (T-POU.NOW)/1000000 
        else:
            pt = 1000
            
        yield from self._finish_unload(pt,move_t)

class GRGate(STL):
    closed = POU.input(False,hidden=True)
    forbid = POU.input(False,hidden=True)
    lock = POU.input(False)
    manual = POU.var(False)
    unloading = POU.var(False)
    open = POU.output(False,hidden=True)
    dr = POU.var(int(0))
    count = POU.var(int(0))    
    select = POU.var( int(0),persistent=True )
    
    def __init__(self,gates: list[MSGate] = [] ):
        super().__init__()
        self.gates = gates
        self._select = -1

    def simple(self,pt: int=15,move_t: int=15):
        self.log(f'старт выгрузки через затвор #{self.select}')
        self.gates[self.select].simple(pt,move_t)
    
    def __call__(self):
        with self:
            for gate in self.gates:
                gate.lock = self.lock
                gate.manual = self.manual
                
            try:
                gate = self.gates[self.select]
                self.unloading = gate.unloading
                self.closed =gate.closed
                self.open = gate.open
                if self._select==self.select:
                    gate.dr = self.dr
                    gate.count = self.count
                else:
                    self.dr = gate.dr
                    self.count = gate.count
                    self._select = self.select
            except Exception as e:
                self.log(e)

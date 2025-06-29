from pyplc.stl import *
from pyplc.pou import POU
from pyplc.channel import Channel
from pyplc.utils.misc import TOF

class iGATE(STL):
    open = POU.input(False,hidden=True)
    close =POU.input(False,hidden=True)
    opened=POU.output(False,hidden=True)
    middle=POU.output(False,hidden=True)
    closed=POU.output(False,hidden=True)
    def __init__(self,open=False,close=False,opened:bool=False,closed:bool=True,middle:bool=None,simple=False):
        super( ).__init__( )
        self.pos = 0
        self.open = open
        self.close= close
        self.opened = opened.force if opened is not None else None
        self.closed = closed.force if closed is not None else None
        self.middle = middle.force if middle is not None else None
        self.simple = simple
    def __call__(self, open=None,close=None):
        with self:
            open = open if open is not None else self.open 
            close = close if close is not None else self.close 
            if open and self.pos<20:
                self.pos+=1
            if (close or (self.simple and not open)) and self.pos>0:
                self.pos-=1
            self.closed = self.pos==0
            self.opened = self.pos==20
            self.middle = 8<self.pos<12

class iMOTOR(STL):
    on = POU.input(False,hidden=True)
    off = POU.input(False,hidden=True)
    ison = POU.output(False,hidden=True)
    def __init__(self,simple=False,on:bool=False,off:bool=False,ison:Channel=None):
        super().__init__( )
        self.simple = simple
        self.on = on
        self.off = off
        self.ison = ison.force if ison is not None else False
    def __call__(self, on=None,off=None):
        with self:
            on = on if on is not None else self.on 
            off = off if off is not None else self.off 
            if self.simple:
                self.ison = on
            else:
                if on:
                    self.ison = True
                elif off:
                    self.ison = False

class iWEIGHT(STL):
    loading = POU.input(False,hidden=True)
    unloading =POU.input(False,hidden=True)
    q = POU.output(0,hidden=True)
    
    def __init__(self,speed=10,loading = False,unloading=False,q: int = None):
        super().__init__( )
        self.q = q.force if q is not None else None
        self.loading = loading
        self.unloading = unloading 
        self.speed = speed
    def __call__(self,  loading=None, unloading=None):
        with self:
            if loading is not None: self.loading = loading 
            if unloading is not None: unloading = self.unloading 
            if self.loading:
                self.q = self.q+self.speed if self.q+self.speed<65535 else 65535
            if self.unloading:
                self.q = self.q-self.speed if self.q-self.speed>0 else 0
            return self.q

class iVALVE(STL):
    open = POU.input(False,hidden=True)
    closed=POU.output(False,hidden=True)
    opened=POU.output(False,hidden=True)
    def __init__(self,open=False,closed:bool=None,opened:bool=None):
        super().__init__( )
        self.closed = closed.force if closed is not None else None
        self.opened = opened.force if opened is not None else None
        self.open = open
    def __call__(self, open=None):
        with self:
            open = open if open is not None else self.open
            self.closed = not open
            self.opened = open 

class iELEVATOR(STL):
    up = POU.input(False,hidden=True)
    down=POU.input(False,hidden=True)
    below=POU.output(False,hidden=True)
    above=POU.output(False,hidden=True)
    middle=POU.output(False,hidden=True)

    def __init__(self,up:bool=False,down:bool=False,below:Channel=None, above:Channel=None, middle:bool=None, moveT=200,id:str=None,parent:POU=None):
        super( ).__init__( id,parent )
        self.pos = 0
        self.up = up
        self.down = down
        self.below = below.force
        self.above = above.force
        self.middle = False if middle is None else middle.force 
        self.moveT = moveT
    def __call__(self, up=None,down=None):
        with self:
            up = self.overwrite('up',up)
            down = self.overwrite('down',down)
            
            if up and self.pos<self.moveT:
                self.pos+=1
            if down and self.pos>0:
                self.pos-=1
            self.below = self.pos==0
            self.above = self.pos>=self.moveT
            self.middle = self.pos==round(self.moveT/2)

class iROTARYFLOW(STL):
    """Имитация роторного расходомера. Имитирует импульсы(clk) и счетчик импульсов(q)
    """
    loading = POU.input(False,hidden=True)
    q = POU.output(0,hidden=True)
    clk = POU.output(False,hidden=True)
    
    def __init__(self, limit=255, speed=10, loading:bool = False,q: int = None,clk: bool = None ,id:str = None, parent: POU = None):
        super().__init__( id,parent )
        self.q = q.force if q is not None else None
        self.clk = clk.force if clk is not None else None
        self.loading = TOF(lambda: loading(),pt=2000)
        self.limit = limit
        self.speed = speed
        self._skip = 0
        
    def __call__(self):
        with self:
            if self.loading:
                self._skip = (self._skip + 1) % self.speed
                if self._skip==0:
                    self.clk = True
                else:
                    self.clk = False
                self.q = self.q+1 if self.q is not None and self.q<self.limit else 0

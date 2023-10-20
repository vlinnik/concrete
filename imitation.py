from pyplc.stl import *

@stl(inputs=['open','close'],outputs=['opened','closed'])
class iGATE(STL):
    def __init__(self,open=False,close=False,simple=False):
        self.pos = 0
        self.open = open
        self.close= close
        self.opened = False
        self.closed = False
        self.simple = simple
    def __call__(self, open=None,close=None):
        with self:
            open = self.overwrite('open',open)
            close = self.overwrite('close',close)
            if open and self.pos<20:
                self.pos+=1
            if (close or (self.simple and not open)) and self.pos>0:
                self.pos-=1
            self.closed = self.pos==0
            self.opened = self.pos==20

@stl(inputs=['on','off'],outputs=['ison'])
class iMOTOR(STL):
    def __init__(self,simple=False,on=False,off=False,ison=False):
        self.simple = simple
        self.on = on
        self.off = off
        self.ison = ison
    def __call__(self, on=None,off=None):
        with self:
            on = self.overwrite('on',on)
            off = self.overwrite('off',off)
            if self.simple:
                self.ison = on
            else:
                if on:
                    self.ison = True
                elif off:
                    self.ison = False

@stl(inputs=['loading','unloading'],outputs=['q'])
class iWEIGHT(STL):
    def __init__(self,speed=10,loading = False,unloading=False):
        self.q = 0
        self.loading = loading
        self.unloading = unloading 
        self.speed = speed
    def __call__(self,  loading=None, unloading=None):
        with self:
            loading = self.overwrite('loading',loading)
            unloading = self.overwrite('unloading',unloading)
            if self.loading:
                self.q = self.q+self.speed if self.q+self.speed<65535 else 65535
            if self.unloading:
                self.q = self.q-self.speed if self.q-self.speed>0 else 0
            return self.q

@stl(inputs=['open'],outputs=['closed','opened'])
class iVALVE(STL):
    def __init__(self,open=False):
        self.closed = True
        self.opened = False
        self.open = open
    def __call__(self, open=None):
        with self:
            open = self.overwrite('open',open)
            self.closed = not open
            self.opened = open 

@stl(inputs=['up','down'],outputs=['below','above','middle'])
class iELEVATOR(STL):
    def __init__(self,up=False,down=False,moveT=200):
        self.pos = 0
        self.up = up
        self.down = down
        self.below = False
        self.above = False
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

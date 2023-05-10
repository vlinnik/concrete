from pyplc.sfc import *
from .dosator import Dosator
from .mixer import Mixer
from .factory import Factory
from .elevator import Elevator

class Readiness():
    """Контроль за группой событий
    Событие - это логичисккий флаг. Для того чтобы получить выход q=True необходимо чтобы все хоть раз стали True
    После того как q=True флаги событий сбрасываются и работа начинается по новому 
    """
    def __init__(self, rails: list):
        self.rails = rails
        self.already = [False]*len(rails)
        self.q = False

    def __call__(self, rst: bool = False):
        n = 0
        any_true = False
        for x in self.rails:
            y = False
            if isinstance(x,Mixer):
                y = x.load
            elif isinstance(x,Dosator):
                y = x.loaded
            elif isinstance(x,Elevator):
                y = x.loaded
                
            self.already[n] = self.already[n] or y
            any_true = any_true or y
            n += 1
        self.q = all(self.already) and not any_true
        if self.q or rst:
            self.already = [False] * len(self.already)
        return self.q

class Loaded():
    """Контроль за группой событий
    Событие - это логичисккий флаг. Для того чтобы получить выход q=True необходимо чтобы все хоть раз стали True
    После того как q=True флаги событий сбрасываются и работа начинается по новому 
    """
    def __init__(self, rails: list):
        self.rails = rails
        self.already = [False]*len(rails)
        self.q = False

    def __call__(self, rst: bool = False):
        n = 0
        any_true = False
        for x in self.rails:
            y = False
            if hasattr(x,'unloaded'):
                y = x.unloaded
            self.already[n] = self.already[n] or y
            any_true = any_true or y
            n += 1
        self.q = all(self.already) and not any_true
        if self.q or rst:
            self.already = [False] * len(self.already)
        return self.q

"""Управление приготовлением бетона
"""
@sfc()
class Manager(SFC):
    def __init__(self, loaded: Readiness, unloaded: Readiness, dosators=[Dosator],mixer: Mixer =None, factory: Factory = None):
        self.dosators = dosators
        self.mixer = mixer
        self.factory = factory
        self.ready = True
        self.targets = list[ tuple ]
        self.loaded = loaded
        self.unloaded = unloaded        

    @sfcaction
    def main( self):
        self.log('initial state')
        yield self.until(lambda: self.mixer.go, step = 'initial')
        self.ready = False

        self.log('starting up job')
        while self.mixer.ready:
            for d in self.dosators:
                d.go = self.mixer.go
                d.count = self.mixer.count
            yield True
        
        self.log('waiting for completition')
        while not self.mixer.ready:
            for d in self.dosators:
                d.unload = self.loaded.q
                
        self.ready = True
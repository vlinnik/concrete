from pyplc.sfc import *
from pyplc.stl import *
from .dosator import Dosator
from .mixer import Mixer
from .elevator import Elevator,ElevatorGeneric

class Readiness():
    """Контроль за группой событий
    Событие - это логичиский флаг. Для того чтобы получить выход q=True необходимо чтобы все хоть раз стали True
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
            elif isinstance(x,ElevatorGeneric):
                y = x.loaded
                
            self.already[n] = self.already[n] or y
            any_true = any_true or y
            n += 1
        self.q = all(self.already) and not any_true
        if self.q or rst:
            print('readyness active')
            self.already = [False] * len(self.already)
        return self.q

class Loaded():
    """Контроль за группой событий
    Событие - это логичиский флаг. Для того чтобы получить выход q=True необходимо чтобы все хоть раз стали True
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

@stl(outputs=['q'])
class Multiplexor():
    def __init__(self,count: int, initial: None, prefix:str = 'in_', obj: POU = None):
        self.obj = self if obj is None else obj
        self.index = 0
        self.count = count
        self.prefix = prefix
        self.keys = [f'{prefix}{i}' for i in range(1,count+1)]
        for i in range(1,count+1):
            obj.export(self.keys[i-1],initial)
        self.q = initial
        
    def __call__(self,index = None):
        with self:
            index = self.overwrite('index',index)
            if index>=1 and index<=self.count:
                self.q = getattr(self.obj,self.keys[index-1])
            else:
                self.q = None
        return self.q

"""Управление приготовлением бетона 
"""
@sfc()
class Manager(SFC):
    def __init__(self, collected: Readiness, loaded: Loaded, mixer: Mixer, dosators: list[Dosator]=[], addons = [] ):
        """Управление процессом приготовления 

        Args:
            collected (Readiness): определение готовности компонентов для приготовления
            loaded (Loaded): определение окочания загрузки
            mixer (Mixer): смеситель, в котором идет приготовление
            dosators (list[Dosator], optional): Дозаторы, в которые происходит набор компонентов.Defaults to [].
            addons (list, optional): объекты с аттрибутом go,count,unload. Defaults to [].
        """
        self.addons = addons   
        self.dosators = dosators
        self.mixer = mixer
        self.ready = True
        self.collected = collected        
        self.loaded = loaded     
        self.targets = []
        
    def emergency(self,value: bool = True ):
        self.log(f'emergency = {value}')
        
    @sfcaction
    def precollect(self):
        for i in self.till(lambda: self.mixer.forbid):
            yield i
            
        self.log('starting up pre-collecting')
        for d in self.dosators:
            d.go = True
            d.count = 1
        yield True
        
    @sfcaction
    def main( self):
        self.log('initial state')
        
        for d in self.dosators:
            d.go = False
            d.unload = False
        yield True
            
        for i in self.until(lambda: self.mixer.go, step = 'initial'):
            yield i
        self.ready = False
        self.log('waiting for dosators get ready')        
        steady = False
        for i in self.until(lambda: steady):
            steady = True
            for d in self.dosators:
                steady = steady and d.ready
            yield i
        self.log('dosators are ready now. preparing...')
        for d in self.dosators:
            d.go = True
            d.count = 1
            for c in d.containers:
                c.err = 0

        batch = 0
        while batch<self.mixer.count:
            self.log(f'starting batch #{batch+1}')
               
            self.log('waiting for dosators collecting')
            for i in self.until( lambda: self.collected.q):
                yield i
            self.log('everything collected')
            
            for i in self.till(lambda: self.mixer.breakpoint, step = 'breakpoint'):
                yield True
                
            self.mixer.loading = True

            for d in self.dosators:
                d.go = False

            if batch+1<self.mixer.count:
                self.exec(self.precollect( ))

            for a in self.addons:
                a.unload = True
                for i in self.until(lambda: a.unloading):
                    yield i
                a.unload = False
                
            for d in self.dosators:
                d.unload = True
                            
            for i in self.until( lambda: self.loaded.q): # пока не загрузим в смеситель
                yield i

            batch+=1
            self.mixer.loaded = True
                    
        self.ready = True
        
class Lock():
    """Блокировка с таймером. Условие активации блокировки задается параметром key"""    
    def __init__(self,delay: int = 4, key: callable = None):
        self.delay = delay*1000000000
        self.q = False
        self._x = None
        self._key = key
        
    def __call__(self, key: bool=None) -> bool:
        if callable(self._key)  and key is None:
            key = self._key( )
            
        if key:
            self.q = True
            self._x = time.time_ns()
        elif self._x is not None:
            self.q = (time.time_ns() - self._x)<self.delay
        else:
            self.q = False
            
        return self.q

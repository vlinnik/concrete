from pyplc.sfc import *
from pyplc.stl import *
from pyplc.utils.latch import RS
from .dosator import Dosator,ManualDosator
from .mixer import Mixer
from .elevator import ElevatorGeneric

class Readiness():
    """Контроль за группой событий
    Событие - это логичиский флаг. Для того чтобы получить выход q=True необходимо чтобы все хоть раз стали True
    После того как q=True флаги событий сбрасываются и работа начинается по новому 
    """
    def __init__(self, rails: list):
        self.rails = rails
        self.already = [False]*len(rails)
        self.q = False

    def clear(self,*_):
        self.already = [False]*len(self.rails)
        self.q = False
        
    def __str__(self):
        return str(self.already)
        
    def __call__(self, rst: bool = False):
        n = 0
        any_true = False
        for x in self.rails:
            y = False
            if isinstance(x,Mixer):
                y = x.load
            elif hasattr(x,'loaded'):
                y = x.loaded
            elif isinstance(x,Readiness):
                y = x.q
            else:
                y = True
                
            self.already[n] = self.already[n] or y
            any_true = any_true or y
            n += 1
        self.q = all(self.already) and not any_true
        if self.q or rst:
            self.already = [False] * len(self.already)
        return self.q

class Loaded():
    """Контроль за группой событий
    Событие - это логический флаг. Для того чтобы получить выход q=True необходимо чтобы все хоть раз стали True
    После того как q=True флаги событий сбрасываются и работа начинается по новому 
    """
    def __init__(self, rails: list):
        self.rails = rails
        self.already = [False]*len(rails)
        self.q = False

    def __str__(self):
        return str(self.already)

    def clear(self,*_):
        self.already = [False]*len(self.rails)
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

class Multiplexor(POU):
    q = POU.output(False)
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

class Manager(SFC):
    """Управление приготовлением бетона 
    """
    def __init__(self, collected: Readiness, loaded: Loaded, mixer: Mixer, dosators: list[Dosator]=[],loadOrder: 'Callable[[], Generator]' = None ,id:str=None,parent:POU=None):
        """Управление приготовлением бетона на 1 смесителе

        Args:
            collected (Readiness): Триггер "все набрано"
            loaded (Loaded): Триггер "все загружено"
            mixer (Mixer): Смеситель, которым управляем
            dosators (list[Dosator], optional): Список задействованных дозаторов. Ждем .ready, ставим .go и .unload (если loadOrder = None) [].
            loadOrder (Callable[[], Generator], optional): функция-генератор, пользовательский вариант загрузки в смеситель. Defaults to None.
            id (str, optional): обычно не надо ставить. Defaults to None.
            parent (POU, optional): для future needs. Defaults to None.
        """
        super( ).__init__( id,parent )
        self.dosators = dosators
        self.mixer = mixer
        self.ready = True
        self.collected = collected
        self.loaded = loaded     
        self.targets = []
        self.order = loadOrder
        self.f_collected = RS(set = lambda: collected.q )
        self.subtasks = [self.f_collected]
        
    def emergency(self,value: bool = True ):
        self.log(f'аварийный режим = {value}')
        self.ready = True
        self.collected.clear( )
        self.loaded.clear( )
        self.sfc_reset = value
        
    def precollect(self):
        while not self.ready:
            yield from self.until( lambda: self.collected.q )
            yield from self.till( lambda: self.mixer.forbid )

            self.log('запуск предварительного набора')
            steady = True
            for _ in self.till(lambda: steady):
                steady = False
                for d in self.dosators:
                    steady = steady or d.go
                yield
            self.log('дозаторы могут начать набор')
            
            if not self.ready:
                for d in self.dosators:
                    d.go = True
        self.log('преднабор больше не нужен')
        
    def main( self):
        self.log('начальное состояние')
        
        for d in self.dosators:
            d.go = False
            d.unload = False
        yield

        self.ready = True            
        yield from self.until(lambda: self.mixer.go, step = 'initial')
        self.ready = False
        self.log('ждем готовности дозаторов...')
        steady = False
        for _ in self.until(lambda: steady):
            steady = True
            for d in self.dosators:
                steady = steady and d.ready
            yield
        self.log('дозаторы готовы, запуск...')
        for d in self.dosators:
            d.go = True
            d.count = 1
            if hasattr(d,'containers'):
                for c in d.containers:
                    c.err = 0
        batch = 0
        job = self.exec(self.precollect( ))

        if self.mixer in self.collected.rails:
            collected = self.collected
        else:
            collected = Readiness([self.collected,self.mixer])
            self.subtasks.append(collected)
        
        while batch<self.mixer.count:
            steady = True
            for _ in self.till(lambda: steady):
                steady = False
                for d in self.dosators:
                    steady = steady or d.ready
                yield
            for d in self.dosators:
                d.go = False            
            self.log(f'начало замеса #{batch+1}')
            yield from self.until( lambda: self.f_collected.q )
            if batch+1>=self.mixer.count:
                self.log('преднабор больше не нужен')
                job.close( )
                
            self.log(f'все набрано #{batch+1}')
            self.f_collected.unset( )
            yield from self.until( lambda: collected.q )
                
            self.log(f'смеситель готов для #{batch+1}')
            
            yield from self.till(lambda: self.mixer.breakpoint, step = 'breakpoint')
                
            self.mixer.loading = True
            if not self.order:
                for d in self.dosators:
                    d.unload = True
            else:
                yield from self.order()
                
            yield from self.until( lambda: self.loaded.q)

            batch+=1
            self.mixer.loaded = True
                    
        self.ready = True
        self.subtasks.remove(collected)
        
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
            self._x = POU.NOW
        elif self._x is not None:
            self.q = (POU.NOW - self._x)<self.delay
        else:
            self.q = False
            
        return self.q

# concrete

concrete - библиотека для написания логики управления БСУ (управления бетонным заводом)
Использует библиотеку PYPLC, используется для контроллера KRAX-PLC932.

## Установка

Просто клонируйте concrete в дерево проекта, в каталог с программой (обычно каталог src)

```bash
git clone https://github.com/vlinnik/concrete.git ./concrete
```

## Использование

```python
from concrete import Motor,MSGate
from concrete.imitation import iMOTOR,iGATE
from board import version,name

instances = [] #here should be listed user defined programs

factory_1 = Factory()
# смеситель №1 + затвор
motor_1 = Motor(powered=plc.MIXER_ON_1, ison=plc.MIXER_ISON_1)
gate_1 = MSGate(closed=plc.MIXER_CLOSED_1, open=plc.MIXER_OPEN_1,opened=plc.MIXER_OPENED_1)
```

## Принять участие

Библиотека приведена как пример использования PYPLC для разработки программы под контроллер KRAX-PLC932.

## Лицензия

MIT License

Copyright (c) 2022 Линник В.В.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

[MIT](https://choosealicense.com/licenses/mit/)
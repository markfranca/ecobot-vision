# Arquitetura ESP32-CAM + Visao Computacional + Servo

## Recomendacao principal

Use tres responsabilidades separadas:

1. ESP32-CAM: apenas transmite imagem em `http://IP_DA_CAMERA:81/stream`.
2. Notebook: roda Python, OpenCV/YOLO e decide quando existe lixo.
3. Arduino ou ESP32 separado: recebe comando simples e move o servo.

A opcao mais simples e estavel para projeto academico e ligar o controlador do
servo por USB no notebook e comunicar por Serial. Assim voce nao depende de dois
dispositivos Wi-Fi respondendo ao mesmo tempo e fica facil ver logs pela IDE do
Arduino.

## Fluxo

1. Python le os frames da ESP32-CAM.
2. YOLO detecta objetos no notebook.
3. Se a confianca for maior que o limite, por exemplo `0.60`, a deteccao vale.
4. O Python espera o cooldown, por exemplo `3` segundos, para evitar repeticao.
5. O Python envia `PICK` ao Arduino/ESP32 do servo.
6. O controlador faz: `0 graus -> 90 graus -> espera 1 segundo -> 0 graus`.

## Rodar com Serial USB

Carregue o sketch:

```text
firmware/arduino_servo_serial/arduino_servo_serial.ino
```

Descubra a porta:

```bash
ls /dev/ttyUSB* /dev/ttyACM*
```

Rode a deteccao:

```bash
source .venv/bin/activate
python src/detect_and_control_servo.py \
  --source http://172.16.100.182:81/stream \
  --weights yolov8n.pt \
  --conf 0.60 \
  --cooldown 3 \
  --servo-mode serial \
  --serial-port /dev/ttyUSB0
```

Se estiver usando Windows, a porta costuma ser algo como `COM3`.

Com modelo treinado para lixo, troque os pesos:

```bash
python src/detect_and_control_servo.py \
  --source http://172.16.100.182:81/stream \
  --weights runs/trash-detector/weights/best.pt \
  --conf 0.60 \
  --cooldown 3 \
  --servo-mode serial \
  --serial-port /dev/ttyUSB0
```

## Testar sem servo

Use `--servo-mode none` para ver se a deteccao esta funcionando sem mandar
comando fisico:

```bash
python src/detect_and_control_servo.py \
  --source http://172.16.100.182:81/stream \
  --weights yolov8n.pt \
  --conf 0.60 \
  --cooldown 3 \
  --servo-mode none
```

## Opcao HTTP com outro ESP32

Carregue o sketch:

```text
firmware/esp32_servo_http/esp32_servo_http.ino
```

Edite no sketch:

```cpp
const char* WIFI_SSID = "SEU_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA";
```

Quando o ESP32 iniciar, veja o IP no monitor serial. Depois rode:

```bash
python src/detect_and_control_servo.py \
  --source http://172.16.100.182:81/stream \
  --weights yolov8n.pt \
  --conf 0.60 \
  --cooldown 3 \
  --servo-mode http \
  --servo-url http://IP_DO_ESP32_SERVO
```

## Ligacao do servo

Servo pequeno SG90:

- Sinal: pino 9 no Arduino, ou pino 13 no ESP32 do sketch HTTP.
- VCC: 5V.
- GND: GND.

Servo MG995:

- Nao alimente o MG995 pelo 5V do Arduino/ESP32.
- Use fonte externa 5V a 6V com corrente suficiente, idealmente 2A ou mais.
- Ligue o positivo da fonte no fio VCC do servo.
- Ligue o GND da fonte no GND do servo.
- Ligue tambem o GND da fonte ao GND do Arduino/ESP32.
- Ligue apenas o fio de sinal do servo ao pino do controlador.

Sem GND comum, o sinal PWM pode ficar instavel. Com alimentacao fraca, o servo
pode tremer, resetar a placa ou travar.

## Classes de lixo

Se usar `runs/trash-detector/weights/best.pt` treinado no dataset de lixo,
qualquer deteccao pode ser considerada lixo.

Se usar `yolov8n.pt`, ele e um modelo generico. Nesse caso voce pode limitar as
classes aceitas:

```bash
python src/detect_and_control_servo.py \
  --source http://172.16.100.182:81/stream \
  --weights yolov8n.pt \
  --trash-classes bottle,cup \
  --conf 0.60 \
  --servo-mode serial \
  --serial-port /dev/ttyUSB0
```

## Melhoria opcional: esquerda, centro e direita

O script pode usar a posicao horizontal do objeto no frame:

```bash
python src/detect_and_control_servo.py \
  --source http://172.16.100.182:81/stream \
  --weights runs/trash-detector/weights/best.pt \
  --conf 0.60 \
  --cooldown 3 \
  --servo-mode serial \
  --serial-port /dev/ttyUSB0 \
  --send-direction
```

Nesse modo:

- Objeto no terco esquerdo: envia `LEFT`.
- Objeto no terco central: envia `CENTER`.
- Objeto no terco direito: envia `RIGHT`.

O sketch Serial interpreta esses comandos como 45, 90 e 135 graus.

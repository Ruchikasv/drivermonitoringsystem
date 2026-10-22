/*
  =============================================================================
  MQ-3 Alcohol Vapor Sensor — Arduino Nano Sketch
  Intelligent Driver Monitoring & Fleet Safety Management System
  =============================================================================

  Wiring Connections:
  -------------------
  MQ-3 Sensor Pin       Arduino Nano Pin
  ----------------      ----------------
  VCC               ->  5V (External or Nano 5V pin)
  GND               ->  GND
  AO (Analog Out)   ->  A0
  DO (Digital Out)  ->  D2

  Output Format (9600 Baud):
  --------------------------
  Analog: <analog_val> | Digital: <0|1>
  Example: Analog: 70 | Digital: 1

  Interval:
  ---------
  Samples and prints every 250 ms (~4 Hz).
  =============================================================================
*/

// Pin definitions
const int MQ3_ANALOG_PIN  = A0;  // Analog input pin connected to MQ-3 AO
const int MQ3_DIGITAL_PIN = 2;   // Digital input pin connected to MQ-3 DO

// Timing configuration
const unsigned long SAMPLE_INTERVAL_MS = 250;  // Sample every 250 ms
unsigned long lastSampleTime = 0;

void setup() {
  // Initialize USB serial communication at 9600 baud
  Serial.begin(9600);

  // Configure digital pin as input
  pinMode(MQ3_DIGITAL_PIN, INPUT);

  // Optional: A0 analog pin configuration
  pinMode(MQ3_ANALOG_PIN, INPUT);

  // Sensor warm-up notice
  // Note: MQ-3 uses an internal heater coil. Fresh power-up requires a brief warm-up period.
  Serial.println(F("# MQ-3 Alcohol Sensor Initialized."));
  Serial.println(F("# Notice: Sensor heater stabilizing..."));
  
  // Brief startup delay for ADC stabilization
  delay(1000);
}

void loop() {
  unsigned long currentTime = millis();

  // Non-blocking timer check: print reading every 250 ms
  if (currentTime - lastSampleTime >= SAMPLE_INTERVAL_MS) {
    lastSampleTime = currentTime;

    // Read raw 10-bit ADC value (0 - 1023)
    int analogValue = analogRead(MQ3_ANALOG_PIN);

    // Read digital threshold pin (HIGH=1 clean / LOW=0 threshold triggered)
    int digitalValue = digitalRead(MQ3_DIGITAL_PIN);

    // Print reading in exact expected format: "Analog: <val> | Digital: <val>"
    Serial.print(F("Analog: "));
    Serial.print(analogValue);
    Serial.print(F(" | Digital: "));
    Serial.println(digitalValue);
  }
}

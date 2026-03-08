## What I need
A windows program **Where Songs Meet** that converts MIDI files (.mid) into macro commands (.mcr) for playing musical instruments in games like Where Winds Meet.
The program should allow to play macro keys directly or export it to a .mcr file to use a third party app.
The program should have a clean and responsive UI.

## Features
- Reads standard MIDI files
- Maps MIDI notes to game keyboard controls
- Generates .mcr format macro files
- Preserves timing and rhythm from the original MIDI
- Supports tempo adjustments and transposition
- Compatible with macro automation tools

## Game Key Mappings

The script maps MIDI notes to three pitch ranges based on the MIDI note number:

**High Pitch (C6 and above, MIDI 84+)**:
- **C** → Q
- **C#** → SHIFT + Q
- **D** → W
- **D#** → CTRL + Q
- **E** → E
- **F** → R
- **F#** → SHIFT + R
- **G** → T
- **G#** → SHIFT + T
- **A** → Y
- **A#** → CTRL + Y
- **B** → U

**Medium Pitch (C5-B5, MIDI 72-83)**:
- **C** → A
- **C#** → SHIFT + A
- **D** → S
- **D#** → CTRL + S
- **E** → D
- **F** → F
- **F#** → SHIFT + F
- **G** → G
- **G#** → SHIFT + G
- **A** → H
- **A#** → CTRL + H
- **B** → J

**Low Pitch (C4 and below, MIDI 0-71)**:
- **C** → Z
- **C#** → SHIFT + Z
- **D** → X
- **D#** → CTRL + X
- **E** → C
- **F** → V
- **F#** → SHIFT + V
- **G** → B
- **G#** → SHIFT + B
- **A** → N
- **A#** → CTRL + N
- **B** → M

Modifier keys (SHIFT, CTRL) are combined with the base key in the macro output.

## Using the Generated Macro

The script generates a `.mcr` file in the following format:

```
Keyboard : ControlLeft : KeyDown
DELAY : 2
Keyboard : M : KeyDown
Keyboard : M : KeyUp
Keyboard : ControlLeft : KeyUp
Keyboard : B : KeyDown
DELAY : 2
Keyboard : B : KeyUp
Keyboard : B : KeyDown
DELAY : 2
Keyboard : B : KeyUp
Keyboard : ControlLeft : KeyDown
DELAY : 2
Keyboard : M : KeyDown
Keyboard : M : KeyUp
Keyboard : ControlLeft : KeyUp
```

### Format Explanation

- `DELAY : <milliseconds>` - Wait for the specified number of milliseconds
- `Keyboard : <key> : KeyDown` - Press the specified key down
- `Keyboard : <key> : KeyUp` - Release the specified key
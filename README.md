# O.T.I.S.

**O.T.I.S.** stands for **Operational Technician for Incompetent Student**.

O.T.I.S. is a personal AI assistant project inspired by **J.A.R.V.I.S.**, Tony Stark's AI from the Iron Man and Marvel movies.  
The long-term goal is to build a real home-hosted assistant capable of speech interaction, local reasoning, system orchestration, visual perception, facial recognition, and multi-device control.

## Project Vision

O.T.I.S. is designed to evolve from a simple voice assistant into a complete personal intelligence system.

The final objective is to create an AI that can:

- listen and respond naturally through voice
- run locally on dedicated hardware
- detect when someone enters the room
- identify known users through facial recognition
- interact with multiple computers and devices on a local network
- act as a central control system for a personal environment
- provide a polished interface inspired by the **Stark Industries** aesthetic

## Current Status

At the moment, O.T.I.S. is in its early core development stage.

The first major milestone completed is:

- local high-quality **Text-to-Speech** using **Kokoro**
- stable local audio playback
- no dependency on paid cloud TTS APIs for the current voice pipeline

## Current Stack

- **Python 3.12**
- **Kokoro** for local text-to-speech
- **Pygame** for audio playback
- **SoundFile** for WAV generation
- **PyCharm** as development environment
- **Windows** as the current development platform

## Planned Infrastructure

O.T.I.S. is currently being developed on a laptop, but the long-term plan is to host it on a dedicated **HP ProDesk running Ubuntu**.

That machine is intended to become the central node of the system, handling:

- AI orchestration
- local services
- voice processing
- vision modules
- future device communication

## Planned Features

### Voice
- Speech-to-Text
- Text-to-Speech
- wake word or activation system
- natural conversational responses

### Intelligence
- LLM-based reasoning
- contextual memory
- command execution
- assistant-style decision making

### Vision
- camera input
- presence detection
- facial recognition
- user-aware behavior

### System Control
- local PC control
- multi-device communication
- interaction with laptops and desktops on the same network
- future hardware and room automation possibilities

### Interface
- Stark Industries-inspired design
- live status display
- clean technical dashboard

## Roadmap

- improve console output and core class structure
- add Speech-to-Text
- connect a first LLM
- build a clean O.T.I.S. core architecture
- migrate the assistant to the HP ProDesk
- add camera-based perception
- expand toward multi-device control

## Notes

This project is both a technical challenge and a long-term personal engineering build.  
The goal is not to copy J.A.R.V.I.S. exactly, but to build a real, functional assistant inspired by that vision.

## Author

Created by **niJaM-sys**.

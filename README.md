# CipherCaller
A program for encrypted voice transmission and its evaluation

### Capabilities
> [!NOTE]
> This program is still in the early stages of development. This description covers currrent capabilities, however more features are on the way!

In the present moment, the program is able to stream an input file between two containers over UDP. Optional AES encryption is available through the example plugin. Below is a brief road map of upcoming features:
- [x] Basic file stream between containers
- [x] Cryptography plug-in system
- [ ] Dropped datagram detection
- [ ] Example plugins
- [ ] Performance measurement system
- [ ] Real-time simulation for file input
- [ ] Microphone input
- [ ] Speaker output


### Basic usage
To use this program, simply navigate to its root directory and issue the `docker compose up` command. You can change the program's behaviour by modifying [`config.yaml`](/config.yaml). Basic information about fields and their functions is supplied through comments in the file itself. For further information please see the project's github wiki.

### Ackgnowledgements
This program is part of my engineer's dissertation. Its structure and some mechanics are based on a [framework](https://github.com/sebsow9/Framework) co-developed with [sebsow9](https://github.com/sebsow9) to learn the ropes of AV transmissions in preparation for our further endeavours.

### License
This program is distributed under the GNU GPL v3 license, which you can find [here](/LICENSE).

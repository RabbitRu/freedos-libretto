; SPDX-License-Identifier: GPL-2.0-or-later
; Minimal BIOS LBA MBR for the generated test disk (partition at LBA 2048).
bits 16
cpu 8086
org 600h
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 7c00h
    cld
    mov si, 7c00h
    mov di, 600h
    mov cx, 256
    rep movsw
    jmp 0:relocated
relocated:
    sti
    mov [unit], dl
    mov si, packet
    mov ah, 42h
    int 13h
    jc failed
    mov dl, [unit]
    mov si, 600h + 446
    jmp 0:7c00h
failed:
    mov si, message
.next:
    lodsb
    test al, al
    jz .halt
    mov ah, 0eh
    mov bx, 7
    int 10h
    jmp .next
.halt:
    cli
    hlt
    jmp .halt
unit: db 0
message: db 'Libretto: cannot read FAT32 boot sector',0
align 4
packet: db 10h,0
    dw 1,7c00h,0
    dd 2048,0
times 446 - ($-$$) db 0
times 64 db 0
dw 0aa55h

; SPDX-License-Identifier: GPL-2.0-or-later
bits 16
cpu 8086
org 100h
    mov ax, 5301h
    xor bx, bx
    int 15h
    mov ax, 530eh
    xor bx, bx
    mov cx, 0102h
    int 15h
    mov ax, 5307h
    mov bx, 1
    mov cx, 3
    int 15h
    mov ax, 4c01h
    int 21h

; SPDX-License-Identifier: GPL-2.0-or-later
; Calibrate REP accounting independently of the memory functions.
bits 16
cpu 386
org 100h
    push cs
    pop ds
    push cs
    pop es
    cld
%macro measure 2
    mov si,source
    mov di,destination
    mov cx,%2
    mov eax,4c424547h
    rep %1
    mov eax,4c454e44h
%endmacro
%macro counts 1
    measure %1,0
    measure %1,1
    measure %1,64
    measure %1,1024
%endmacro
    counts movsb
    counts movsw
    counts movsd
    mov ax,4c00h
    int 21h
source times 4096 db 0a5h
destination times 4096 db 0

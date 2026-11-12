; SPDX-License-Identifier: GPL-2.0-or-later
; Minimal alternate CLOCK$ for exercising the real DOS device chain.
bits 16
cpu 8086
org 0
    dd 0ffffffffh
    dw 8008h
    dw strategy,interrupt
    db 'CLOCK$  '
strategy:
    mov [cs:req],bx
    mov [cs:req+2],es
    retf
interrupt:
    push ax
    push bx
    push cx
    push si
    push di
    push ds
    push es
    les bx,[cs:req]
    mov ax,0100h
    cmp byte [es:bx+2],0
    je .init
    cmp word [es:bx+18],6
    jne .bad
    cmp byte [es:bx+2],4
    je .read
    cmp byte [es:bx+2],8
    je .write
.bad:
    mov ax,8105h
    jmp .done
.init:
    mov word [es:bx+14],resident_end
    mov word [es:bx+16],cs
    jmp .done
.read:
    push es
    push bx
    les di,[es:bx+14]
    push cs
    pop ds
    mov si,record
    mov cx,6
    cld
    rep movsb
    pop bx
    pop es
    jmp .done
.write:
    push ds
    push si
    lds si,[es:bx+14]
    push es
    push bx
    push cs
    pop es
    mov di,record
    mov cx,6
    cld
    rep movsb
    pop bx
    pop es
    pop si
    pop ds
.done:
    mov [es:bx+3],ax
    pop es
    pop ds
    pop di
    pop si
    pop cx
    pop bx
    pop ax
    retf
req dd 0
record dw 0
       db 0,0,0,0
resident_end:

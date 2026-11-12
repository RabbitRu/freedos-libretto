; SPDX-License-Identifier: GPL-2.0-or-later
; Deterministic INT 1Ah source; ordinary DOS INT 21h still enters the kernel.
bits 16
cpu 386
segment _TEXT class=CODE
global _clock_start, _clock_stop, _clock_ticks, _clock_stat
_clock_start:
    pusha
    push ds
    push es
    mov ax,351ah
    int 21h
    mov [cs:previous],bx
    mov [cs:previous+2],es
    push cs
    pop ds
    mov dx,hook
    mov ax,251ah
    int 21h
    pop es
    pop ds
    popa
    ret
_clock_stop:
    pusha
    push ds
    lds dx,[cs:previous]
    mov ax,251ah
    int 21h
    pop ds
    popa
    ret
; void __cdecl clock_ticks(unsigned long ticks,unsigned midnight,unsigned step)
_clock_ticks:
    push bp
    mov bp,sp
    push ax
    mov ax,[bp+4]
    mov [cs:ticks],ax
    mov ax,[bp+6]
    mov [cs:ticks+2],ax
    mov ax,[bp+8]
    mov [cs:midnight],al
    mov ax,[bp+10]
    mov [cs:step],ax
    mov dword [cs:reads],0
    mov dword [cs:writes],0
    pop ax
    pop bp
    ret
; unsigned long __cdecl clock_stat(unsigned index)
; 0 reads, 1 writes, 2 current ticks, 3 RTC time CX:DX, 4 RTC date CX:DX.
_clock_stat:
    push bp
    mov bp,sp
    push bx
    mov bx,[bp+4]
    shl bx,2
    mov ax,[cs:reads+bx]
    mov dx,[cs:reads+bx+2]
    pop bx
    pop bp
    ret
hook:
    pushf
    cmp ah,0
    je .read
    cmp ah,1
    je .write
    cmp ah,3
    je .rtc_time
    cmp ah,5
    je .rtc_date
    popf
    jmp far [cs:previous]
.read:
    popf
    inc dword [cs:reads]
    mov dx,[cs:ticks]
    mov cx,[cs:ticks+2]
    xor ax,ax
    mov al,[cs:midnight]
    mov byte [cs:midnight],0
    push ax
    mov ax,[cs:step]
    add [cs:ticks],ax
    adc word [cs:ticks+2],0
    pop ax
    iret
.write:
    popf
    inc dword [cs:writes]
    mov [cs:ticks],dx
    mov [cs:ticks+2],cx
    mov byte [cs:midnight],0
    jmp .success
.rtc_time:
    popf
    mov [cs:rtc_time],dx
    mov [cs:rtc_time+2],cx
    jmp .success
.rtc_date:
    popf
    mov [cs:rtc_date],dx
    mov [cs:rtc_date+2],cx
.success:
    push bp
    mov bp,sp
    and word [ss:bp+6],0fffeh
    pop bp
    iret
previous dd 0
; Keep these five dwords contiguous for clock_stat.
reads dd 0
writes dd 0
ticks dd 0
rtc_time dd 0
rtc_date dd 0
midnight db 0
step dw 0

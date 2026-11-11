; SPDX-License-Identifier: GPL-2.0-or-later
; Call the actual kernel object with its Pascal ABI, including DF=1 on entry.
bits 16
cpu 386
segment _TEXT class=CODE
global _checked
extern MEMCPY, FMEMCPY, MEMSET, FMEMSET

; unsigned __cdecl checked(op, far dest, far src, count, fill);
_checked:
    push bp
    mov bp,sp
    pushfd
    pushad
    push ds
    push es
    push fs
    push gs
    mov [cs:saved_sp],sp
    mov [cs:saved_ds],ds
    mov word [cs:result],0
    mov ax,1357h
    mov fs,ax
    mov ax,2468h
    mov gs,ax
    mov ax,3456h
    mov es,ax
    mov ebx,0b1b21234h
    mov ecx,0c1c22345h
    mov edx,0d1d23456h
    mov esi,51514567h
    mov edi,61615678h
    movzx ebp,bp
    or ebp,71710000h
    mov [cs:saved_bp],ebp
    std
    cmp word [ss:bp+4],0
    je .near_copy
    cmp word [ss:bp+4],1
    je .far_copy
    cmp word [ss:bp+4],2
    je .near_fill
    push word [ss:bp+8]
    push word [ss:bp+6]
    push word [ss:bp+16]
    push word [ss:bp+14]
    mov eax,0a1a20000h
    call FMEMSET
    jmp .verify
.near_fill:
    push word [ss:bp+6]
    push word [ss:bp+16]
    push word [ss:bp+14]
    mov eax,0a1a20000h
    call MEMSET
    jmp .verify
.far_copy:
    push word [ss:bp+8]
    push word [ss:bp+6]
    push word [ss:bp+12]
    push word [ss:bp+10]
    push word [ss:bp+14]
    mov eax,0a1a20000h
    call FMEMCPY
    jmp .verify
.near_copy:
    push word [ss:bp+6]
    push word [ss:bp+10]
    push word [ss:bp+14]
    mov eax,0a1a20000h
    call MEMCPY
.verify:
    cmp sp,[cs:saved_sp]
    je .stack_ok
    mov word [cs:result],1
    mov sp,[cs:saved_sp]
.stack_ok:
    shr eax,16
    cmp ax,0a1a2h
    jne .bad_register
    cmp ebx,0b1b21234h
    jne .bad_register
    cmp ecx,0c1c22345h
    jne .bad_register
    cmp edx,0d1d23456h
    jne .bad_register
    cmp esi,51514567h
    jne .bad_register
    cmp edi,61615678h
    jne .bad_register
    cmp ebp,[cs:saved_bp]
    jne .bad_register
    mov ax,ds
    cmp ax,[cs:saved_ds]
    jne .bad_register
    mov ax,es
    cmp ax,3456h
    jne .bad_register
    mov ax,fs
    cmp ax,1357h
    jne .bad_register
    mov ax,gs
    cmp ax,2468h
    je .registers_ok
.bad_register:
    or word [cs:result],2
.registers_ok:
    pushf
    pop ax
    test ax,400h
    jz .df_ok
    or word [cs:result],4
.df_ok:
    cld
    pop gs
    pop fs
    pop es
    pop ds
    popad
    popfd
    pop bp
    mov ax,[cs:result]
    ret
saved_sp dw 0
saved_ds dw 0
saved_bp dd 0
result dw 0

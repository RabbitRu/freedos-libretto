; SPDX-License-Identifier: GPL-2.0-or-later
; Read-only DOS memory probe. Values describe memory WHILE THIS PROBE RUNS.
; Only its own PSP block is shrunk; it never frees another program's block.
bits 16
cpu 386
org 100h
%macro pair 2
    mov dx, %1
    mov cx, %1.len
    call write
    mov eax, [%2]
    call decimal
    mov dx, crlf
    mov cx, 2
    call write
%endmacro
start:
    mov sp, stack_top
    mov bx, (image_end - $$ + 100h + 15) / 16
    mov ax, cs
    mov es, ax
    mov ah, 4ah
    int 21h
    jc failure
    mov dword [probe_bytes], ((image_end - $$ + 100h + 15) / 16) * 16
    mov ax, 3306h
    int 21h
    and dh, 10h
    setnz byte [in_hma]
    mov ax, 5802h
    int 21h
    jc .no_umb
    and eax, 1
    mov [umb_linked], eax
.no_umb:
    mov ah, 52h
    int 21h
    mov si, [es:bx-2]
    mov bp, 8192
.scan:
    mov es, si
    mov al, [es:0]
    cmp al, 'M'
    je .valid
    cmp al, 'Z'
    jne failure
.valid:
    cmp word [es:1], 0
    jne .next
    movzx eax, word [es:3]
    shl eax, 4
    cmp si, 0a000h
    jae .upper
    add [conv_free], eax
    cmp eax, [conv_largest]
    jbe .next
    mov [conv_largest], eax
    jmp .next
.upper:
    add [umb_free], eax
.next:
    cmp byte [es:0], 'Z'
    je .xms
    movzx eax, si
    movzx edx, word [es:3]
    add eax, edx
    inc eax
    cmp eax, 0ffffh
    ja failure
    mov si, ax
    dec bp
    jnz .scan
    jmp failure
.xms:
    mov ax, 4300h
    int 2fh
    cmp al, 80h
    jne .ems
    mov dword [xms_present], 1
    mov ax, 4310h
    int 2fh
    mov [xms_entry], bx
    mov [xms_entry+2], es
    mov ah, 08h
    call far [xms_entry]
    cmp bl, 0
    jne .ems
    movzx eax, ax
    mov [xms_largest], eax
    movzx eax, dx
    mov [xms_free], eax
.ems:
    mov dx, ems_device
    mov ax, 3d00h
    int 21h
    jc .report
    mov bx, ax
    mov ah, 3eh
    int 21h
    mov ah, 40h
    int 67h
    test ah, ah
    jnz .report
    mov ah, 42h
    int 67h
    test ah, ah
    jnz .report
    mov dword [ems_present], 1
    movzx eax, bx
    mov [ems_free_pages], eax
    movzx eax, dx
    mov [ems_total_pages], eax
.report:
    pair k_probe, probe_bytes
    pair k_conv, conv_free
    pair k_largest, conv_largest
    pair k_linked, umb_linked
    pair k_umb, umb_free
    pair k_hma, in_hma
    pair k_xms, xms_present
    pair k_xmsfree, xms_free
    pair k_xmslargest, xms_largest
    pair k_ems, ems_present
    pair k_emsfree, ems_free_pages
    pair k_emstotal, ems_total_pages
    mov ax, 4c00h
    int 21h
failure:
    mov dx, err
    mov cx, err.len
    call write
    mov ax, 4c01h
    int 21h
write:
    push ax
    push bx
    mov bx, 1
    mov ah, 40h
    int 21h
    pop bx
    pop ax
    ret
decimal:
    pushad
    mov di, number_end
    mov ebx, 10
.loop:
    xor edx, edx
    div ebx
    add dl, '0'
    dec di
    mov [di], dl
    test eax, eax
    jnz .loop
    mov dx, di
    mov cx, number_end
    sub cx, di
    call write
    popad
    ret
%macro key 2
%1: db %2, '='
.len equ $ - %1
%endmacro
key k_probe, 'probe_psp_block_bytes'
key k_conv, 'conventional_free_bytes_while_probe_loaded'
key k_largest, 'largest_conventional_block_bytes_while_probe_loaded'
key k_linked, 'umb_chain_linked'
key k_umb, 'linked_umb_free_bytes'
key k_hma, 'dos_in_hma'
key k_xms, 'xms_present'
key k_xmsfree, 'xms_free_kib'
key k_xmslargest, 'xms_largest_kib'
key k_ems, 'ems_present'
key k_emsfree, 'ems_free_16k_pages'
key k_emstotal, 'ems_total_16k_pages'
err: db 'probe_error=1',13,10
.len equ $ - err
ems_device: db 'EMMXXXX0',0
crlf: db 13,10
xms_entry: dd 0
probe_bytes: dd 0
conv_free: dd 0
conv_largest: dd 0
umb_linked: dd 0
umb_free: dd 0
in_hma: dd 0
xms_present: dd 0
xms_free: dd 0
xms_largest: dd 0
ems_present: dd 0
ems_free_pages: dd 0
ems_total_pages: dd 0
number: times 12 db 0
number_end:
    times 2048 db 0
stack_top:
image_end:

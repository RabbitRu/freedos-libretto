; File:
;                         asmsupt.asm
; Description:
;       Assembly support routines for miscellaneous functions
;
;                    Copyright (c) 1995, 1998
;                       Pasquale J. Villani
;                       All Rights Reserved
;
; This file is part of DOS-C.
;
; DOS-C is free software; you can redistribute it and/or
; modify it under the terms of the GNU General Public License
; as published by the Free Software Foundation; either version
; 2, or (at your option) any later version.
;
; DOS-C is distributed in the hope that it will be useful, but
; WITHOUT ANY WARRANTY; without even the implied warranty of
; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See
; the GNU General Public License for more details.
;
; You should have received a copy of the GNU General Public
; License along with DOS-C; see the file COPYING.  If not,
; write to the Free Software Foundation, 675 Mass Ave,
; Cambridge, MA 02139, USA.
;
; version 1.4 by tom.ehlert@ginko.de
; added some more functions
; changed bcopy, scopy, sncopy,...
; to      memcpy, strcpy, strncpy
; Bart Oldeman: optimized a bit: see /usr/include/bits/string.h from 
; glibc 2.2
;
; $Id: asmsupt.asm 1568 2011-04-09 02:42:51Z bartoldeman $
;

; for OW on Linux:
%ifdef owlinux
%define WATCOM
%endif

%ifdef WATCOM
%ifdef _INIT
%define WATCOM_INIT ; no seperate init segment for watcom.
%endif
%endif

%ifndef WATCOM_INIT

		%include "segs.inc"
		%include "stacks.inc"

%ifdef _INIT

  segment INIT_TEXT
  %define  FMEMCPYBACK INIT_FMEMCPYBACK
  %define   MEMCPY   INIT_MEMCPY
  %define  FMEMCPY  INIT_FMEMCPY
  %define   MEMSET   INIT_MEMSET
  %define  FMEMSET  INIT_FMEMSET
  %define   STRCPY   INIT_STRCPY
  %define  FSTRCPY  INIT_FSTRCPY
  %define   STRLEN   INIT_STRLEN
  %define  FSTRLEN  INIT_FSTRLEN
  %define  FMEMCHR  INIT_FMEMCHR
  %define  FSTRCHR  INIT_FSTRCHR
  %define   STRCHR   INIT_STRCHR
  %define  FSTRCMP  INIT_FSTRCMP
  %define   STRCMP   INIT_STRCMP
  %define FSTRNCMP INIT_FSTRNCMP
  %define  STRNCMP  INIT_STRNCMP
  %define  FMEMCMP  INIT_FMEMCMP
  %define   MEMCMP   INIT_MEMCMP

%else
  
  segment HMA_TEXT

%endif

;*********************************************************************
; this implements some of the common string handling functions
;
; every function has 1 entry
;
;   NEAR FUNC()
;
; currently done:
;
; fmemcpyBack(void FAR *dest, void FAR *src, int count)
;  memcpy(void     *dest, void     *src, int count)
; fmemcpy(void FAR *dest, void FAR *src, int count)
;  memset(void *dest, int ch, int count);
; fmemset(void FAR *dest, int ch, int count);
;  strcpy (void    *dest, void     *src);
; fstrcpy (void FAR*dest, void FAR *src);
;  strlen (void    *dest);
; fstrlen (void FAR*dest);
; fmemchr (BYTE FAR *src , int ch);
; fstrchr (BYTE FAR *src , int ch);
;  strchr (BYTE     *src , int ch);
; fstrcmp (BYTE FAR *s1 , BYTE FAR *s2);
;  strcmp (BYTE     *s1 , BYTE     *s2);
; fstrncmp(BYTE FAR *s1 , BYTE FAR *s2, int count);
;  strncmp(BYTE     *s1 , BYTE     *s2, int count);
; fmemcmp(BYTE FAR *s1 , BYTE FAR *s2, int count);
;  memcmp(BYTE     *s1 , BYTE     *s2, int count);

;***********************************************
; pascal_setup - set up the standard calling frame for C-functions
;                and save registers needed later
;                also preload the args for the near functions
;                di=arg1
;                si=arg2
;                cx=arg3
;
pascal_setup:
                pop     ax                      ; get return address
                
                push    bp                      ; Standard C entry
                mov     bp,sp
%ifdef WATCOM
                push    bx
                push    cx
                push    es
%endif
                push    si
                push    di
                push    ds
                ; Set both ds and es to same segment (for near copy)
                push    ds
                pop     es

                ; Set direction to autoincrement
                cld

                mov bl,6       ; majority (4) wants that
arg arg1, arg2, arg3
                mov cx,[.arg3] ; majority (8) wants that (near and far)
                mov si,[.arg2] ; majority (3) wants that (near)
                mov di,[.arg1] ; majority (3) wants that (near)
                
                jmp ax



        
; Memory operations set up their own arguments directly.  This avoids the
; CALL/POP/indirect-JMP dispatcher and unused near-argument loads in far calls.
%macro memory_setup 0
                push    bp
                mov     bp,sp
%ifdef WATCOM
                push    bx
                push    cx
                push    es
%endif
                push    si
                push    di
                push    ds
                cld
%endmacro

;***********************************************
;
;       VOID memcpy(REG BYTE *s, REG BYTE *d, REG COUNT n);
;
                global  MEMCPY
MEMCPY:
                memory_setup
                push    ds
                pop     es
arg d, s, n
                mov     cx,[.n]
                mov     si,[.s]
                mov     di,[.d]
                mov     bl,6

domemcpy:
%if XCPU >= 386
                cmp     cx,128
                jae     memcpy_large
%endif
memcpy_words:
                ; And do the built-in byte copy, but do a 16-bit transfer
                ; whenever possible.
                shr     cx,1
                rep     movsw
                jnc     memcpy_return
                movsb
memcpy_return:
%if 0                           ; only needed for fmemcpyback
                cld
%endif        

;
; pascal_return - pop saved registers and do return
;
        
                jmp short pascal_return



;************************************************************
;
;       VOID fmemcpy(REG BYTE FAR *d, REG BYTE FAR *s,REG COUNT n);
;       VOID fmemcpyBack(REG BYTE FAR *d, REG BYTE FAR *s,REG COUNT n);
;
                global  FMEMCPY
%if 0
                global  FMEMCPYBACK
FMEMCPYBACK:
                std             ; force to copy the string in reverse order
%endif
FMEMCPY:
                memory_setup
arg {d,4}, {s,4}, n
                mov     cx,[.n]
                lds     si,[.s]
                les     di,[.d]
                mov     bl,10
                jmp     domemcpy

;***************************************************************
;
;       VOID fmemset(REG VOID FAR *d, REG BYTE ch, REG COUNT n);
;
                global  FMEMSET
FMEMSET:
                memory_setup
arg {d,4}, ch, n
                mov     cx,[.n]
                mov     ax,[.ch]
                les     di,[.d]
                mov     bl,8

domemset:
%if XCPU >= 386
                cmp     cx,128
                jae     memset_large
%endif
memset_words:
                mov     ah,al
                shr     cx,1
                rep     stosw
                jnc     pascal_return
                stosb
                jmp     short pascal_return

; Near fill uses the same destination segment as the C data segment.
                global  MEMSET
MEMSET:
                memory_setup
                push    ds
                pop     es
arg d, ch, n
                mov     cx,[.n]
                mov     ax,[.ch]
                mov     di,[.d]
                mov     bl,6
                jmp     domemset

;*****
pascal_return:
                lds     di, [bp]    ; return address in ds, saved bp in di
                mov     bh, 0
                add     bp, bx      ; point bp to "as if there were 0 args"
                mov     [bp+2], ds  ; put return address at first arg
                mov     [bp], di    ; saved bp below that one

                pop     ds
                pop     di
                pop     si
%ifdef WATCOM
                pop     es
                pop     cx
                pop     bx
%endif
                mov     sp,bp
                pop     bp
                ret

;*****************************************************************
                
; fstrcpy (void FAR*dest, void FAR *src);

                global  FSTRCPY
FSTRCPY:
                call pascal_setup

arg {dest,4}, {src,4}
                ; Get the source pointer, ss
                lds   si,[.src]

                ; and the destination pointer, d
                les   di,[.dest]

		mov   bl,8
                
                jmp short dostrcpy

;******
                global  STRCPY
STRCPY:
                call pascal_setup


%ifdef PASCAL
                ; Get the source pointer, ss
                mov   si,[bp+4]

                ; and the destination pointer, d
                mov   di,[bp+6]
%endif
		mov   bl,4

dostrcpy:

strcpy_loop:                
                lodsb
                stosb
                test al,al
                jne  strcpy_loop
                
		jmp  short pascal_return

;******************************************************************                
                global  FSTRLEN
FSTRLEN:
                call pascal_setup

                ; Get the source pointer, ss
                les   di,[bp+4]
		mov   bl,4

                jmp short dostrlen

;**********************************************
                global  STRLEN
STRLEN:
                call pascal_setup
                ; Get the source pointer, ss
%ifdef PASCAL
                mov   di,[bp+4]
%endif
		mov   bl,2

dostrlen:           
                mov al,0
                mov cx,0xffff
                repne scasb

                mov ax,cx
                not ax                
                dec ax

                jmp short pascal_return

;************************************************************
; strchr (BYTE *src , int ch);

                global  STRCHR
STRCHR:
                call pascal_setup

                ; Get the source pointer, ss
arg src, ch
%ifdef STDCALL	; preset above for PASCAL
                mov             cx,[.ch]
                mov             si,[.src]
%endif
		mov bl,4

strchr_loop:                
                lodsb
                cmp  al,cl
                je   strchr_found
                test al,al
                jne  strchr_loop
                
strchr_retzero:
                xor ax, ax               ; return NULL if not found
                mov dx, ax               ; for fstrchr()
                jmp short pascal_return
                
strchr_found:
                mov ax, si
                mov dx, ds               ; for fstrchr()
strchr_found1:
                dec ax

                jmp short pascal_return

%ifndef _INIT

;*****
;  fstrchr (BYTE     far *src , int ch);
                global  FSTRCHR
FSTRCHR:
                call pascal_setup

arg {src,4}, ch
                ; Get ch (preset above)
                ;mov cx, [bp+4]
                
                ;and the source pointer, src
                lds si, [.src]

		;mov	bl, 6 - preset above

                jmp short strchr_loop

;******
                global  FMEMCHR
FMEMCHR:
                call pascal_setup

arg {src,4}, ch, n
                ; Get the length - preset above
%ifdef STDCALL
                mov cx, [.n]
%endif

                ; and the search value
                mov ax, [.ch]

                ; and the source pointer, ss
                les di, [.src]

		mov bl, 8

		jcxz strchr_retzero
                repne scasb
                jne strchr_retzero
                mov dx, es
                mov ax, di
                jmp short strchr_found1

;**********************************************************************
                global  FSTRCMP
FSTRCMP:
                call pascal_setup

arg {dest,4}, {src,4}
                ; Get the source pointer, ss
                lds             si,[.src]

                ; and the destination pointer, d
                les             di,[.dest]
                
                mov bl,8

%if 0
                jmp short dostrcmp

;******
                global STRCMP
STRCMP:
                call pascal_setup

                mov bl,4

                ; Get the source pointer, ss
                ; mov             si,[bp+4]

                ; and the destination pointer, d
                ; mov             di,[bp+6]
                xchg si,di

dostrcmp:                       
%endif
                                    ; replace strncmp(s1,s2)-->
                                    ;         strncmp(s1,s2,0xffff)
                mov cx,0xffff
%if 0
                jmp short dostrncmp

                
;**********************************************************************
                global  FSTRNCMP
FSTRNCMP:
                call pascal_setup

                ; Get the source pointer, ss
                lds             si,[bp+4]

                ; and the destination pointer, d
                les             di,[bp+8]
                mov             cx,[bp+12]
                mov             bl,10
                
                jmp short dostrncmp

;******
                global  _strncmp
_strncmp:
                call pascal_setup

                ; Get the source pointer, ss
                ;mov             si,[bp+4]

                ; and the destination pointer, d
                ;mov             di,[bp+6]
                ;mov             cx,[bp+8]
                xchg si,di

dostrncmp:
%endif
                jcxz strncmp_retzero

strncmp_loop:                
                lodsb
                scasb
                jne  strncmp_done
                test al,al
                loopne   strncmp_loop
                jmp  short strncmp_retzero		
%endif

;**********************************************************************
; fmemcmp(BYTE FAR *s1 , BYTE FAR *s2, int count);
                global  FMEMCMP
FMEMCMP:
                call pascal_setup

arg {dest,4}, {src,4}, n
                ; the length - preset above
%ifdef STDCALL
                mov cx, [.n]
%endif
                
                ; Get the source pointer, ss
                les di,[.src]

                ; and the destination pointer, d
                lds si,[.dest]

		mov bl,10

                jmp short domemcmp

;******
;  memcmp(BYTE     *s1 , BYTE     *s2, int count);        
                global  MEMCMP
MEMCMP:
                call pascal_setup

                ; all preset: Get the source pointer, ss
                ;mov             si,[bp+6]

                ; and the destination pointer, d
                ;mov             di,[bp+8]
                ;mov             cx,[bp+4]
		;mov		 bl,6
                xchg si,di

domemcmp:
                jcxz strncmp_retzero
                repe cmpsb
                jne  strncmp_done
strncmp_retzero:
                xor  ax, ax
                jmp  short strncmp_done2
strncmp_done:
                lahf
		ror  ah,1
strncmp_done2:  jmp  pascal_return

; Long blocks use 32-bit operands with 16-bit addresses/counts.
; Keep the word path for short blocks, close overlap and segment-offset wrap.
; In particular, no dword may straddle offset FFFF in real mode.
%if XCPU >= 386
memcpy_large:
                mov     ax,si
                add     ax,cx
                jc      memcpy_words
                mov     ax,di
                add     ax,cx
                jc      memcpy_words
                ; A positive physical overlap of 1..3 bytes must retain
                ; the word path's propagation.  Testing the low 16 bits
                ; of ES*16+DI-(DS*16+SI) is conservative: it can also
                ; reject distant blocks, but never misses that overlap.
                push    dx
                mov     ax,es
                mov     dx,ds
                sub     ax,dx
                shl     ax,4
                add     ax,di
                sub     ax,si
                pop     dx
                cmp     ax,3
                jbe     memcpy_words
                ; Align stores.  Source loads may be unaligned, but the
                ; range checks above ensure they never cross offset FFFF.
                test    di,3
                jz      .aligned
                test    di,1
                jz      .word_align
                movsb
                dec     cx
.word_align:
                test    di,2
                jz      .aligned
                movsw
                sub     cx,2
.aligned:
                mov     ax,cx
                shr     cx,2
                rep     movsd
                jnc     .byte
                movsw
.byte:
                test    al,1
                jz      .done
                movsb
.done:
                jmp     pascal_return

memset_large:
                mov     si,di
                add     si,cx
                jc      memset_words
                mov     ah,al
                test    di,3
                jz      .aligned
                test    di,1
                jz      .word_align
                stosb
                dec     cx
.word_align:
                test    di,2
                jz      .aligned
                stosw
                sub     cx,2
.aligned:
                ; Watcom's kernel entry does not save high GPR halves.
                ; Preserve high EAX while forming the four-byte pattern.
                push    eax
                push    ax
                push    ax
                pop     eax
                mov     si,cx
                shr     cx,2
                rep     stosd
                jnc     .byte
                stosw
.byte:
                test    si,1
                jz      .done
                stosb
.done:
                pop     eax
                jmp     pascal_return
%endif

%endif

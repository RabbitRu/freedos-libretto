; SPDX-License-Identifier: GPL-2.0-or-later
bits 16
org 100h
; Trace each successfully executed INSTALL to the host, independently of DOS.
mov al, 'I'
out 0e9h, al
int 20h

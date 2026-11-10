/* SPDX-License-Identifier: GPL-2.0-or-later
 * QEMU 8.2 plugin. Inline counters are safe only with one vCPU/thread,
 * which install and the runner both enforce. Markers delimit guest workloads.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "qemu-plugin.h"

QEMU_PLUGIN_EXPORT int qemu_plugin_version = QEMU_PLUGIN_VERSION;
static uint64_t total, non_rom, first_total, first_non_rom, interval;
static bool active;
static unsigned errors;
static FILE *output;

static void begin(unsigned int cpu, void *udata)
{
    (void)cpu; (void)udata;
    if (active) errors++;
    first_total=total; first_non_rom=non_rom; active=true;
}
static void end(unsigned int cpu, void *udata)
{
    (void)cpu; (void)udata;
    if (!active) { errors++; return; }
    fprintf(output,"%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%u\n",
            ++interval,total-first_total,non_rom-first_non_rom,errors);
    fflush(output); active=false;
}
static void translate(qemu_plugin_id_t id,struct qemu_plugin_tb *tb)
{
    (void)id;
    static const unsigned char begin_bytes[]={0x66,0xb8,0x47,0x45,0x42,0x4c};
    static const unsigned char end_bytes[]={0x66,0xb8,0x44,0x4e,0x45,0x4c};
    for (size_t i=0;i<qemu_plugin_tb_n_insns(tb);i++) {
        struct qemu_plugin_insn *insn=qemu_plugin_tb_get_insn(tb,i);
        uint64_t pc=qemu_plugin_insn_vaddr(insn);
        qemu_plugin_register_vcpu_insn_exec_inline(insn,QEMU_PLUGIN_INLINE_ADD_U64,&total,1);
        /* Address-window metric, NOT a kernel-only or cycle counter. */
        if (pc<0xa0000 || pc>=0x100000)
            qemu_plugin_register_vcpu_insn_exec_inline(insn,QEMU_PLUGIN_INLINE_ADD_U64,&non_rom,1);
        if (qemu_plugin_insn_size(insn)==sizeof(begin_bytes)) {
            const void *bytes=qemu_plugin_insn_data(insn);
            if (!memcmp(bytes,begin_bytes,sizeof(begin_bytes)))
                qemu_plugin_register_vcpu_insn_exec_cb(insn,begin,QEMU_PLUGIN_CB_NO_REGS,NULL);
            else if (!memcmp(bytes,end_bytes,sizeof(end_bytes)))
                qemu_plugin_register_vcpu_insn_exec_cb(insn,end,QEMU_PLUGIN_CB_NO_REGS,NULL);
        }
    }
}
static void finish(qemu_plugin_id_t id,void *udata)
{
    (void)id; (void)udata;
    if (active || errors) fprintf(output,"ERROR,unbalanced_markers,%u\n",errors);
    fclose(output);
}
QEMU_PLUGIN_EXPORT int qemu_plugin_install(qemu_plugin_id_t id,const qemu_info_t *info,int argc,char **argv)
{
    if (!info->system_emulation || info->system.max_vcpus!=1) {
        fputs("Libretto counter requires system emulation with one vCPU.\n",stderr);
        return -1;
    }
    const char *path=NULL;
    for (int i=0;i<argc;i++) {
        if (!strncmp(argv[i],"out=",4)) path=argv[i]+4;
        else return -1;
    }
    if (!path || !(output=fopen(path,"w"))) return -1;
    fputs("interval,guest_instructions,non_rom_instructions,marker_errors\n",output);
    qemu_plugin_register_vcpu_tb_trans_cb(id,translate);
    qemu_plugin_register_atexit_cb(id,finish,NULL);
    return 0;
}

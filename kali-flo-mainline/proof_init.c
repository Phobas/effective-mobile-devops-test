#define _GNU_SOURCE
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/sysinfo.h>
#include <sys/utsname.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <fcntl.h>
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int screen_fd = -1;

static void write_all(int fd, const char *s)
{
    if (fd < 0 || !s) return;
    size_t left = strlen(s);
    while (left) {
        ssize_t n = write(fd, s, left);
        if (n <= 0) return;
        s += n;
        left -= (size_t)n;
    }
}

static void log_both(int fd, const char *s)
{
    write_all(fd, s);
    if (screen_fd >= 0 && screen_fd != fd)
        write_all(screen_fd, s);
}

static void mkdir_ok(const char *p)
{
    if (mkdir(p, 0755) < 0 && errno != EEXIST) {
        /* Keep booting: diagnostics are more important than failing hard. */
    }
}

static void mount_fs(const char *src, const char *target, const char *type,
                     unsigned long flags, const char *data)
{
    if (mount(src, target, type, flags, data) < 0 && errno != EBUSY) {
        /* Best effort. */
    }
}

static void dump_file(int fd, const char *path, size_t max_bytes)
{
    int f = open(path, O_RDONLY);
    if (f < 0) return;
    char buf[512];
    size_t done = 0;
    for (;;) {
        size_t want = sizeof(buf) - 1;
        if (done + want > max_bytes) want = max_bytes - done;
        if (!want) break;
        ssize_t n = read(f, buf, want);
        if (n <= 0) break;
        buf[n] = 0;
        log_both(fd, buf);
        done += (size_t)n;
    }
    close(f);
}

static void list_dir(int fd, const char *path)
{
    DIR *d = opendir(path);
    if (!d) return;
    char line[256];
    snprintf(line, sizeof(line), "\n[%s]\n", path);
    log_both(fd, line);
    struct dirent *de;
    while ((de = readdir(d))) {
        if (!strcmp(de->d_name, ".") || !strcmp(de->d_name, "..")) continue;
        snprintf(line, sizeof(line), "  %s\n", de->d_name);
        log_both(fd, line);
    }
    closedir(d);
}

static void show_info(int fd)
{
    struct utsname u;
    struct sysinfo si;
    char line[512];

    log_both(fd, "\n=== KALI FLO MAINLINE PROOF ===\n");
    if (uname(&u) == 0) {
        snprintf(line, sizeof(line), "Kernel: %s %s %s\n", u.sysname, u.release, u.machine);
        log_both(fd, line);
    }
    if (sysinfo(&si) == 0) {
        unsigned long long total = (unsigned long long)si.totalram * si.mem_unit;
        unsigned long long freeb = (unsigned long long)si.freeram * si.mem_unit;
        snprintf(line, sizeof(line), "RAM: total=%llu MiB free=%llu MiB\n",
                 total / 1024 / 1024, freeb / 1024 / 1024);
        log_both(fd, line);
    }
    log_both(fd, "Cmdline: ");
    dump_file(fd, "/proc/cmdline", 2048);
    log_both(fd, "\n\nMeminfo (first part):\n");
    dump_file(fd, "/proc/meminfo", 1800);
    list_dir(fd, "/sys/class/drm");
    list_dir(fd, "/sys/class/power_supply");
    list_dir(fd, "/sys/class/udc");
    list_dir(fd, "/dev");
    log_both(fd, "\nProof init is alive. No partitions were written by this image.\n");
}

static void serial_console(void)
{
    for (;;) {
        int fd = open("/dev/ttyGS0", O_RDWR | O_NOCTTY);
        if (fd < 0) {
            sleep(1);
            continue;
        }

        write_all(fd, "\r\nKali Flo proof serial online. Commands: info, reboot, poweroff, help\r\n> ");
        char buf[128];
        size_t pos = 0;
        for (;;) {
            char c;
            ssize_t n = read(fd, &c, 1);
            if (n <= 0) break;
            if (c == '\r' || c == '\n') {
                buf[pos] = 0;
                write_all(fd, "\r\n");
                if (!strcmp(buf, "info")) {
                    show_info(fd);
                } else if (!strcmp(buf, "reboot")) {
                    sync();
                    reboot(RB_AUTOBOOT);
                } else if (!strcmp(buf, "poweroff")) {
                    sync();
                    reboot(RB_POWER_OFF);
                } else if (!strcmp(buf, "help") || pos == 0) {
                    write_all(fd, "info | reboot | poweroff | help\r\n");
                } else {
                    write_all(fd, "Unknown command\r\n");
                }
                pos = 0;
                write_all(fd, "> ");
            } else if (c == 8 || c == 127) {
                if (pos) --pos;
            } else if (pos + 1 < sizeof(buf)) {
                buf[pos++] = c;
            }
        }
        close(fd);
    }
}

int main(void)
{
    mkdir_ok("/dev");
    mkdir_ok("/proc");
    mkdir_ok("/sys");
    mkdir_ok("/tmp");

    mount_fs("devtmpfs", "/dev", "devtmpfs", MS_NOSUID, "mode=0755");
    mount_fs("proc", "/proc", "proc", MS_NOSUID | MS_NOEXEC | MS_NODEV, NULL);
    mount_fs("sysfs", "/sys", "sysfs", MS_NOSUID | MS_NOEXEC | MS_NODEV, NULL);

    screen_fd = open("/dev/tty0", O_WRONLY | O_NOCTTY);
    if (screen_fd < 0)
        screen_fd = open("/dev/console", O_WRONLY | O_NOCTTY);

    show_info(screen_fd);
    log_both(screen_fd, "\nWaiting for USB serial gadget (/dev/ttyGS0)...\n");

    serial_console();
    return 0;
}

/* SPDX-FileCopyrightText: 2026 blender-web contributors
 * SPDX-License-Identifier: GPL-3.0-or-later */

#define _GNU_SOURCE

#include <pthread.h>
#include <stdint.h>
#include <stdio.h>

enum {
  PROXY_MAIN_STACK = 32 * 1024 * 1024,
  ORDINARY_DEFAULT_STACK = 8 * 1024 * 1024,
  EXPLICIT_CHILD_STACK = 2 * 1024 * 1024,
};

static size_t current_stack_size(void)
{
  pthread_attr_t attr;
  size_t stack_size = 0;
  if (pthread_getattr_np(pthread_self(), &attr) != 0 ||
      pthread_attr_getstacksize(&attr, &stack_size) != 0)
  {
    return 0;
  }
  pthread_attr_destroy(&attr);
  return stack_size;
}

static void *record_stack_size(void *userdata)
{
  *(size_t *)userdata = current_stack_size();
  return NULL;
}

int main(void)
{
  size_t ordinary_stack = 0;
  size_t explicit_stack = 0;
  pthread_t ordinary_thread;
  pthread_t explicit_thread;
  pthread_attr_t explicit_attr;

  const size_t proxy_stack = current_stack_size();
  int ok = pthread_create(&ordinary_thread, NULL, record_stack_size, &ordinary_stack) == 0;
  if (ok) {
    ok = pthread_join(ordinary_thread, NULL) == 0;
  }
  ok = ok && pthread_attr_init(&explicit_attr) == 0;
  ok = ok && pthread_attr_setstacksize(&explicit_attr, EXPLICIT_CHILD_STACK) == 0;
  if (ok) {
    ok = pthread_create(&explicit_thread, &explicit_attr, record_stack_size, &explicit_stack) == 0;
  }
  pthread_attr_destroy(&explicit_attr);
  if (ok) {
    ok = pthread_join(explicit_thread, NULL) == 0;
  }

  ok = ok && proxy_stack == PROXY_MAIN_STACK && ordinary_stack == ORDINARY_DEFAULT_STACK &&
       explicit_stack == EXPLICIT_CHILD_STACK;
  printf("BW_PTHREAD_STACK_POLICY {\"proxy_main\":%zu,\"ordinary_default\":%zu,"
         "\"explicit_child\":%zu}\n",
         proxy_stack,
         ordinary_stack,
         explicit_stack);
  printf("BW_PTHREAD_STACK_POLICY_RESULT %s\n", ok ? "PASS" : "FAIL");
  return ok ? 0 : 1;
}

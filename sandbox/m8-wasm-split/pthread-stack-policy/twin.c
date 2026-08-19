/* SPDX-FileCopyrightText: 2026 blender-web contributors
 * SPDX-License-Identifier: GPL-3.0-or-later */

#include <pthread.h>

int main(void)
{
  pthread_attr_t attr;
  if (pthread_attr_init(&attr) != 0) {
    return 1;
  }
  pthread_attr_destroy(&attr);
  return 0;
}

/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

#include <cstdio>

#include "IMB_imbuf.hh"

int main()
{
  const blender::IMBWebThreadPolicyStatus bootstrap = blender::IMB_web_thread_policy_apply(0, 1);
  const blender::IMBWebThreadPolicyStatus applied = blender::IMB_web_thread_policy_apply(8, 8);
  const blender::IMBWebThreadPolicyStatus rollback = blender::IMB_web_thread_policy_apply(0, 1);

  std::printf(
      "BW_IMAGE_POLICY_AGGREGATE {\"bootstrap\":{\"openexr_set\":%s,"
      "\"openexr_threads\":%d,\"oiio_set\":%s,\"oiio_threads\":%d},"
      "\"applied\":{\"openexr_set\":%s,\"openexr_threads\":%d,"
      "\"oiio_set\":%s,\"oiio_threads\":%d},\"rollback\":{"
      "\"openexr_set\":%s,\"openexr_threads\":%d,\"oiio_set\":%s,"
      "\"oiio_threads\":%d}}\n",
      bootstrap.openexr_set ? "true" : "false",
      bootstrap.openexr_threads,
      bootstrap.oiio_set ? "true" : "false",
      bootstrap.oiio_threads,
      applied.openexr_set ? "true" : "false",
      applied.openexr_threads,
      applied.oiio_set ? "true" : "false",
      applied.oiio_threads,
      rollback.openexr_set ? "true" : "false",
      rollback.openexr_threads,
      rollback.oiio_set ? "true" : "false",
      rollback.oiio_threads);

  return bootstrap.openexr_set && bootstrap.openexr_threads == 0 && bootstrap.oiio_set &&
                 bootstrap.oiio_threads == 1 && applied.openexr_set &&
                 applied.openexr_threads == 8 && applied.oiio_set && applied.oiio_threads == 8 &&
                 rollback.openexr_set && rollback.openexr_threads == 0 && rollback.oiio_set &&
                 rollback.oiio_threads == 1 ?
             0 :
             1;
}

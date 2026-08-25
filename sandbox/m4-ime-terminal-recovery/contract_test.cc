/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <cstdio>
#include <string>
#include <vector>

#include "GHOST_IMEQueueWeb.hh"

namespace {

using ghost_web::ime::Message;
using ghost_web::ime::MessageKind;
using ghost_web::ime::MessageQueue;
using ghost_web::ime::PublishResult;

bool g_fail_assignment = false;

bool controlled_assign(std::string &destination, const char *text, const size_t text_length)
{
  if (g_fail_assignment) {
    g_fail_assignment = false;
    return false;
  }
  return ghost_web::ime::assign_text(destination, text, text_length);
}

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL: %s\n", message);
  }
  return condition;
}

bool normal_order_contract()
{
  MessageQueue queue;
  queue.set_enabled(true);
  if (!require(queue.publish(MessageKind::Start, "", 0, 0, -1, -1) ==
                   PublishResult::Accepted,
               "normal start") ||
      !require(queue.publish(MessageKind::Update, "ni", 2, 2, 0, 2) ==
                   PublishResult::Accepted,
               "normal update") ||
      !require(queue.publish(MessageKind::Commit, "nihon", 5, -1, -1, -1) ==
                   PublishResult::Accepted,
               "normal commit") ||
      !require(queue.cancel() == PublishResult::Accepted, "normal end"))
  {
    return false;
  }

  std::vector<Message> messages;
  Message message;
  while (queue.consume(message)) {
    messages.push_back(std::move(message));
  }
  return require(messages.size() == 4, "normal message count") &&
         require(messages[0].kind == MessageKind::Start, "normal start order") &&
         require(messages[1].kind == MessageKind::Update && messages[1].text == "ni",
                 "normal update ownership") &&
         require(messages[2].kind == MessageKind::Commit && messages[2].text == "nihon",
                 "normal commit ownership") &&
         require(messages[3].kind == MessageKind::End, "normal end order") &&
         require(queue.published_count() == 4 && queue.consumed_count() == 4 &&
                     queue.dropped_count() == 0,
                 "normal counters");
}

bool saturation_contract()
{
  MessageQueue queue;
  queue.set_enabled(true);
  if (queue.publish(MessageKind::Start, "", 0, 0, -1, -1) != PublishResult::Accepted) {
    return require(false, "saturation start");
  }
  for (uint64_t index = 1; index < MessageQueue::DisposableCapacity; index++) {
    if (queue.publish(MessageKind::Update, "u", 1, 1, -1, -1) !=
        PublishResult::Accepted)
    {
      return require(false, "disposable capacity fill");
    }
  }
  if (!require(queue.publish(MessageKind::Update, "drop", 4, 4, -1, -1) ==
                   PublishResult::Rejected,
               "saturated update rejected") ||
      !require(queue.publish(MessageKind::Commit, "final", 5, -1, -1, -1) ==
                   PublishResult::Accepted,
               "reserved commit accepted") ||
      !require(queue.cancel() == PublishResult::Accepted, "reserved end accepted") ||
      !require(queue.cancel() == PublishResult::Rejected, "full queue rejects duplicate end"))
  {
    return false;
  }

  std::vector<MessageKind> kinds;
  Message message;
  while (queue.consume(message)) {
    kinds.push_back(message.kind);
  }
  return require(kinds.size() == MessageQueue::Capacity, "saturated drain count") &&
         require(kinds[kinds.size() - 2] == MessageKind::Commit, "reserved commit order") &&
         require(kinds.back() == MessageKind::End, "reserved end order") &&
         require(queue.published_count() == MessageQueue::Capacity &&
                     queue.consumed_count() == MessageQueue::Capacity &&
                     queue.dropped_count() == 2,
                 "saturation counters");
}

bool allocation_recovery_contract()
{
  MessageQueue queue(controlled_assign);
  queue.set_enabled(true);
  g_fail_assignment = true;
  if (!require(queue.publish(MessageKind::Update, "owned", 5, 5, -1, -1) ==
                   PublishResult::AllocationFailed,
               "allocation failure diagnosed") ||
      !require(queue.cancel() == PublishResult::Accepted,
               "allocation failure keeps no-allocation cancel capacity"))
  {
    return false;
  }
  Message message;
  return require(queue.consume(message) && message.kind == MessageKind::End,
                 "allocation failure drains explicit end") &&
         require(!queue.consume(message), "allocation recovery drains once") &&
         require(queue.published_count() == 1 && queue.consumed_count() == 1 &&
                     queue.dropped_count() == 1,
                 "allocation recovery counters");
}

bool disabled_and_reuse_contract()
{
  MessageQueue queue;
  if (!require(queue.cancel() == PublishResult::Rejected, "disabled cancel rejected")) {
    return false;
  }
  queue.set_enabled(true);
  Message message;
  for (int round = 0; round < 128; round++) {
    if (queue.publish(MessageKind::Start, "x", 1, 1, -1, -1) != PublishResult::Accepted ||
        queue.cancel() != PublishResult::Accepted || !queue.consume(message) ||
        message.kind != MessageKind::Start || message.text != "x" || !queue.consume(message) ||
        message.kind != MessageKind::End)
    {
      return require(false, "slot reuse");
    }
  }
  return require(queue.published_count() == 256 && queue.consumed_count() == 256 &&
                     queue.dropped_count() == 1,
                 "reuse counters");
}

}  // namespace

int main()
{
  if (!normal_order_contract() || !saturation_contract() ||
      !allocation_recovery_contract() || !disabled_and_reuse_contract())
  {
    return 1;
  }
  std::printf("IME_TERMINAL_QUEUE PASS contracts=4 capacity=64 disposable=62 "
              "terminal=commit,end allocation=cancel reuse=128\n");
  return 0;
}

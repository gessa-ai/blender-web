/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * \ingroup GHOST-web
 * Bounded browser-main to WM-worker IME message ownership queue. */

#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>

namespace ghost_web::ime {

enum class MessageKind : int32_t {
  Start = 0,
  Update = 1,
  Commit = 2,
  End = 3,
};

struct Message {
  MessageKind kind = MessageKind::End;
  std::string text;
  int cursor_position = -1;
  int target_start = -1;
  int target_end = -1;
};

enum class PublishResult {
  Accepted,
  Rejected,
  AllocationFailed,
};

using TextAssignFunction = bool (*)(std::string &destination,
                                    const char *text,
                                    size_t text_length);

inline bool assign_text(std::string &destination, const char *text, const size_t text_length)
{
  try {
    destination.assign(text_length == 0 ? "" : text, text_length);
    return true;
  }
  catch (...) {
    return false;
  }
}

/**
 * Single-producer/single-consumer queue with terminal capacity that disposable
 * composition updates cannot consume. Slots own their strings in-place, so an
 * End/cancel message never allocates and remains publishable after a text
 * allocation failure.
 */
class MessageQueue {
 public:
  static constexpr uint64_t Capacity = 64;
  static constexpr uint64_t CommitCapacity = Capacity - 1;
  static constexpr uint64_t DisposableCapacity = Capacity - 2;

  explicit MessageQueue(TextAssignFunction assign_function = assign_text)
      : assign_function_(assign_function)
  {
  }

  void set_enabled(const bool enabled)
  {
    enabled_.store(enabled, std::memory_order_release);
  }

  PublishResult reject()
  {
    dropped_.fetch_add(1, std::memory_order_relaxed);
    return PublishResult::Rejected;
  }

  PublishResult publish(const MessageKind kind,
                        const char *text,
                        const size_t text_length,
                        const int cursor_position,
                        const int target_start,
                        const int target_end)
  {
    if (!enabled_.load(std::memory_order_acquire)) {
      return reject();
    }

    const uint64_t write_sequence = write_sequence_.load(std::memory_order_relaxed);
    const uint64_t read_sequence = read_sequence_.load(std::memory_order_acquire);
    const uint64_t occupancy = write_sequence - read_sequence;
    const uint64_t capacity = kind == MessageKind::End ? Capacity :
                              kind == MessageKind::Commit ? CommitCapacity :
                                                            DisposableCapacity;
    if (occupancy >= capacity) {
      return reject();
    }

    Slot &slot = slots_[write_sequence % Capacity];
    if (slot.ready.load(std::memory_order_acquire)) {
      return reject();
    }

    std::string owned_text;
    if (kind != MessageKind::End &&
        !assign_function_(owned_text, text_length == 0 ? "" : text, text_length))
    {
      dropped_.fetch_add(1, std::memory_order_relaxed);
      return PublishResult::AllocationFailed;
    }

    slot.message.kind = kind;
    slot.message.text = std::move(owned_text);
    slot.message.cursor_position = cursor_position;
    slot.message.target_start = target_start;
    slot.message.target_end = target_end;
    slot.ready.store(true, std::memory_order_release);
    write_sequence_.store(write_sequence + 1, std::memory_order_release);
    published_.fetch_add(1, std::memory_order_relaxed);
    return PublishResult::Accepted;
  }

  PublishResult cancel()
  {
    return publish(MessageKind::End, nullptr, 0, -1, -1, -1);
  }

  bool consume(Message &message)
  {
    const uint64_t read_sequence = read_sequence_.load(std::memory_order_relaxed);
    Slot &slot = slots_[read_sequence % Capacity];
    if (!slot.ready.load(std::memory_order_acquire)) {
      return false;
    }

    message = std::move(slot.message);
    slot.ready.store(false, std::memory_order_release);
    read_sequence_.store(read_sequence + 1, std::memory_order_release);
    consumed_.fetch_add(1, std::memory_order_relaxed);
    return true;
  }

  uint64_t published_count() const
  {
    return published_.load(std::memory_order_relaxed);
  }

  uint64_t consumed_count() const
  {
    return consumed_.load(std::memory_order_relaxed);
  }

  uint64_t dropped_count() const
  {
    return dropped_.load(std::memory_order_relaxed);
  }

 private:
  struct Slot {
    std::atomic<bool> ready{false};
    Message message;
  };

  std::array<Slot, Capacity> slots_{};
  std::atomic<uint64_t> write_sequence_{0};
  std::atomic<uint64_t> read_sequence_{0};
  std::atomic<uint64_t> published_{0};
  std::atomic<uint64_t> consumed_{0};
  std::atomic<uint64_t> dropped_{0};
  std::atomic<bool> enabled_{false};
  TextAssignFunction assign_function_;
};

}  // namespace ghost_web::ime

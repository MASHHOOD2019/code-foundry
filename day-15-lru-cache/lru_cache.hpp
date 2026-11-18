// Author: Mashhood Ali
// LRU (Least Recently Used) Cache.
//
// A fixed-capacity cache with O(1) get() and put(). The most recently
// used entry sits at the front of an intrusive doubly linked list and
// the least recently used entry at the back; a hash map from key to
// list node makes every lookup constant time. When the cache is full,
// put() evicts the back (least recently used) entry.
//
// Complexity:
//   get() / put()  O(1) average time, O(capacity) space.
//   Eviction       O(1).
//
// Thread safety: none. Wrap get()/put() in a mutex (e.g. std::mutex)
// if the cache is shared across threads.

#pragma once

#include <cstddef>
#include <list>
#include <optional>
#include <stdexcept>
#include <unordered_map>
#include <utility>

template <typename Key, typename Value>
class LruCache {
public:
    explicit LruCache(std::size_t capacity) : capacity_(capacity) {
        if (capacity == 0) {
            throw std::invalid_argument("LRU cache capacity must be > 0");
        }
    }

    // Returns the value for `key` and marks it most recently used,
    // or std::nullopt on a miss.
    std::optional<Value> get(const Key& key) {
        auto it = index_.find(key);
        if (it == index_.end()) {
            return std::nullopt;
        }
        // Move the hit node to the front (most recently used).
        items_.splice(items_.begin(), items_, it->second);
        return it->second->second;
    }

    // Inserts or updates `key`. On a full cache, evicts the least
    // recently used entry.
    void put(Key key, Value value) {
        auto it = index_.find(key);
        if (it != index_.end()) {
            it->second->second = std::move(value);
            items_.splice(items_.begin(), items_, it->second);
            return;
        }
        if (items_.size() == capacity_) {
            const Key& lru_key = items_.back().first;
            index_.erase(lru_key);
            items_.pop_back();
        }
        items_.emplace_front(std::move(key), std::move(value));
        index_.emplace(items_.front().first, items_.begin());
    }

    bool contains(const Key& key) const { return index_.count(key) != 0; }
    std::size_t size() const { return items_.size(); }
    std::size_t capacity() const { return capacity_; }
    bool empty() const { return items_.empty(); }

    void clear() {
        items_.clear();
        index_.clear();
    }

private:
    using Entry = std::pair<Key, Value>;
    using List = std::list<Entry>;

    std::size_t capacity_;
    List items_;  // front = most recently used, back = least recently used
    std::unordered_map<Key, typename List::iterator> index_;
};

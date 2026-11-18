// Author: Mashhood Ali
// Demo + self-check for LruCache (see lru_cache.hpp).
//
// Build:  g++ -std=c++17 -Wall -Wextra -O2 main.cpp -o lru_demo
// Run:    ./lru_demo

#include <cassert>
#include <iostream>
#include <string>

#include "lru_cache.hpp"

int main() {
    LruCache<int, std::string> cache(3);

    cache.put(1, "one");
    cache.put(2, "two");
    cache.put(3, "three");

    // Hit: key 1 becomes most recently used.
    assert(cache.get(1).value_or("") == "one");

    // Cache is full; inserting key 4 evicts key 2 (least recently used).
    cache.put(4, "four");
    assert(!cache.get(2).has_value());
    assert(cache.get(1).value_or("") == "one");
    assert(cache.get(3).value_or("") == "three");
    assert(cache.get(4).value_or("") == "four");
    assert(cache.size() == 3);

    // Updating an existing key refreshes its value and its recency.
    cache.put(3, "THREE");
    assert(cache.get(3).value_or("") == "THREE");

    // Inserting key 5 now evicts key 1, the least recently used.
    cache.put(5, "five");
    assert(!cache.get(1).has_value());
    assert(cache.get(3).value_or("") == "THREE");
    assert(cache.get(4).value_or("") == "four");
    assert(cache.get(5).value_or("") == "five");

    // Misses return std::nullopt; capacity-0 construction is rejected.
    assert(!cache.get(99).has_value());
    bool threw = false;
    try {
        LruCache<int, int> broken(0);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    assert(threw);

    std::cout << "All LRU cache checks passed (capacity 3, "
              << "eviction + update + miss behaviour verified).\n";
    return 0;
}

// Author: Mashhood Ali
//
// Demo for MemoryPool<T>: allocate, free, reuse, grow, and lifetime.
//
// Build:  g++ -std=c++17 -Wall -Wextra -O2 main.cpp -o memory_pool_demo
// Run:    ./memory_pool_demo

#include <cassert>
#include <cstdint>
#include <iostream>
#include <unordered_set>
#include <vector>

#include "memory_pool.hpp"

namespace {

struct Particle {
    double x, y, z;
    int id;
    explicit Particle(int id_in) : x(0.0), y(0.0), z(0.0), id(id_in) {}
};

int destroyed_count = 0;

struct Tracked {
    explicit Tracked(int v) : value(v) {}
    ~Tracked() { ++destroyed_count; }
    int value;
};

void check_allocate_and_values() {
    MemoryPool<Particle, 8> pool;
    std::vector<Particle*> particles;
    for (int i = 0; i < 5; ++i) {
        particles.push_back(pool.create(i));
    }
    assert(pool.live_blocks() == 5);
    for (int i = 0; i < 5; ++i) {
        assert(particles[i]->id == i);
    }
    // Alignment: every pooled address must satisfy alignof(Particle).
    for (const Particle* p : particles) {
        assert(reinterpret_cast<std::uintptr_t>(p) % alignof(Particle) == 0);
    }
    for (Particle* p : particles) {
        pool.destroy(p);
    }
    assert(pool.live_blocks() == 0);
    std::cout << "Allocate + values + alignment check passed.\n";
}

void check_free_block_reuse() {
    MemoryPool<int, 4> pool;
    int* first = pool.create(111);
    int* second = pool.create(222);
    pool.destroy(first);  // frees the block holding 111
    int* reused = pool.create(333);
    // The freed block is at the head of the free list, so it is the
    // next one handed out: same address, new value.
    assert(reused == first);
    assert(*reused == 333);
    pool.destroy(second);
    pool.destroy(reused);
    assert(pool.live_blocks() == 0);
    std::cout << "Free-block reuse check passed: freed address handed out again.\n";
}

void check_chunk_growth() {
    constexpr std::size_t kChunk = 16;
    MemoryPool<int, kChunk> pool;
    std::vector<int*> ptrs;
    for (int i = 0; i < 40; ++i) {  // more than two chunks
        ptrs.push_back(pool.create(i));
    }
    assert(pool.chunk_count() == 3);  // 16 + 16 + 8
    assert(pool.total_blocks() == 48);
    assert(pool.live_blocks() == 40);
    assert(pool.free_blocks() == 8);
    // All addresses must be distinct.
    std::unordered_set<int*> seen(ptrs.begin(), ptrs.end());
    assert(seen.size() == ptrs.size());
    for (int i = 0; i < 40; ++i) {
        assert(*ptrs[i] == i);
        pool.destroy(ptrs[i]);
    }
    assert(pool.live_blocks() == 0);
    assert(pool.free_blocks() == pool.total_blocks());
    std::cout << "Chunk growth check passed: 40 allocations over 3 chunks, "
                 "all values intact, all blocks returned.\n";
}

void check_destructor_runs() {
    destroyed_count = 0;
    MemoryPool<Tracked, 4> pool;
    Tracked* a = pool.create(1);
    Tracked* b = pool.create(2);
    assert(a->value == 1 && b->value == 2);
    pool.destroy(a);
    assert(destroyed_count == 1);
    pool.destroy(b);
    assert(destroyed_count == 2);
    std::cout << "Destructor check passed: destroy() runs the destructor.\n";
}

}  // namespace

int main() {
    check_allocate_and_values();
    check_free_block_reuse();
    check_chunk_growth();
    check_destructor_runs();
    std::cout << "All memory pool checks passed.\n";
    return 0;
}

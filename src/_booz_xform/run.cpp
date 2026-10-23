#include <iostream>
#include "booz_xform.hpp"
#include "parallel.hpp"

using namespace booz_xform;

void Booz_xform::run() {
  if (verbose > 0) {
    std::cout << "compute_surfs (0-based indices): ";
    for (int j = 0; j < compute_surfs.size(); j++) std::cout << " " << compute_surfs[j];
    std::cout << std::endl;
  }

  init();

  if (verbose > 0) {
    std::cout << "                   |        outboard (theta=0)      |      inboard (theta=pi)      |" << std::endl;
    std::cout << "thread js_b js zeta| |B|input  |B|Boozer    Error   | |B|input  |B|Boozer    Error |" << std::endl;
    std::cout << "------------------------------------------------------------------------------------" << std::endl;
  }

  // Surfaces are independent, so they are solved concurrently.
  parallel_for(compute_surfs.size(), [this](int j) { surface_solve(j); });
}

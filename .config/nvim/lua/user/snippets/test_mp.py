import multiprocessing as mp


def target(rank):
    import debugpy

    debugpy.listen(5678 + rank)
    debugpy.wait_for_client()
    a = 2
    b = rank * a
    print(b)
    print(f"Done on {rank=}")


def test():
    procs = [
        mp.Process(target=target, name=f"rank-{rank}", args=(rank,))
        for rank in range(4)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join()


if __name__ == "__main__":
    test()

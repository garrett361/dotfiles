import multiprocessing as mp
import os


def sub_target():
    return 1


def target(rank):
    os.environ["RANK"] = str(rank)
    print(f"Starting on {rank=}")
    a = 2
    b = rank * a
    sub_target()
    print(f"{b=}")
    print(f"Done on {rank=}")


def test():
    target(0)


def test_mp():
    procs = [
        mp.Process(target=target, name=f"rank-{rank}", args=(rank,))
        for rank in range(2)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join()

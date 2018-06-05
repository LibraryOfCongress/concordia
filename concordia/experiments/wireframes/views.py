from django.shortcuts import render


def wireframe(request, page):
    return render(request, "wireframes/{}".format(page))
